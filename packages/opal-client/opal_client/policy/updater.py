import asyncio
import random
from typing import List, Optional

import pydantic
from fastapi_websocket_pubsub import PubSubClient
from fastapi_websocket_pubsub.pub_sub_client import PubSubOnConnectCallback
from fastapi_websocket_rpc.rpc_channel import OnDisconnectCallback, RpcChannel
from opal_client.callbacks.register import CallbacksRegister
from opal_client.callbacks.reporter import CallbacksReporter
from opal_client.config import opal_client_config
from opal_client.data.fetcher import DataFetcher
from opal_client.logger import logger
from opal_client.policy.fetcher import PolicyFetcher, RetryableBundleError
from opal_client.policy.topics import default_subscribed_policy_directories
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.policy_store.policy_store_client_factory import (
    DEFAULT_POLICY_STORE_GETTER,
)
from opal_common.async_utils import TakeANumberQueue, TasksPool
from opal_common.config import opal_common_config
from opal_common.schemas.data import DataUpdateReport
from opal_common.schemas.policy import PolicyBundle, PolicyUpdateMessage
from opal_common.schemas.store import TransactionType
from opal_common.security.sslcontext import get_custom_ssl_context
from opal_common.topics.utils import pubsub_topics_from_directories
from opal_common.utils import get_authorization_header

# Floor for a deferred re-fetch, and the base of its per-round exponential
# backoff. Used when the server did not send a `Retry-After` (or sent a smaller
# one than the round's backoff).
DEFERRED_REFETCH_BASE_SECONDS = 5.0


def _jittered(delay: float) -> float:
    """Spreads a deferred re-fetch uniformly over [delay/2, delay].

    Without this every client that hit the same outage re-fetches on the
    same tick, so the fleet arrives at the server in lockstep and re-
    creates the stampede the backoff exists to prevent. Module-level so
    tests can replace it with the identity function.
    """
    return random.uniform(delay / 2.0, delay)


class PolicyUpdater:
    """Keeps policy-stores (e.g. OPA) up to date with relevant policy code
    (e.g: rego) and static data (e.g: data.json files like in OPA bundles).

    Uses Pub/Sub to subscribe to specific directories in the policy code
    repository (i.e: git), and fetches bundles containing updated policy
    code.
    """

    def __init__(
        self,
        token: str = None,
        pubsub_url: str = None,
        subscription_directories: List[str] = None,
        policy_store: BasePolicyStoreClient = None,
        data_fetcher: Optional[DataFetcher] = None,
        callbacks_register: Optional[CallbacksRegister] = None,
        opal_client_id: str = None,
        on_connect: List[PubSubOnConnectCallback] = None,
        on_disconnect: List[OnDisconnectCallback] = None,
    ):
        """Inits the policy updater.

        Args:
            token (str, optional): Auth token to include in connections to OPAL server. Defaults to CLIENT_TOKEN.
            pubsub_url (str, optional): URL for Pub/Sub updates for policy. Defaults to OPAL_SERVER_PUBSUB_URL.
            subscription_directories (List[str], optional): directories in the policy source repo to subscribe to.
                Defaults to POLICY_SUBSCRIPTION_DIRS. every time the directory is updated by a commit we will receive
                a message on its respective topic. we dedups directories with ancestral relation, and will only
                receive one message for each updated file.
            policy_store (BasePolicyStoreClient, optional): Policy store client to use to store policy code. Defaults to DEFAULT_POLICY_STORE.
        """
        # defaults
        token: str = token or opal_client_config.CLIENT_TOKEN
        pubsub_url: str = pubsub_url or opal_client_config.SERVER_PUBSUB_URL
        self._subscription_directories: List[str] = (
            subscription_directories or opal_client_config.POLICY_SUBSCRIPTION_DIRS
        )
        self._opal_client_id = opal_client_id
        self._scope_id = opal_client_config.SCOPE_ID

        # The policy store we'll save policy modules into (i.e: OPA)
        self._policy_store = policy_store or DEFAULT_POLICY_STORE_GETTER()
        # pub/sub server url and authentication data
        self._server_url = pubsub_url
        self._token = token
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]
        # Pub/Sub topics we subscribe to for policy updates
        if self._scope_id == "default":
            self._topics = pubsub_topics_from_directories(
                self._subscription_directories
            )
        else:
            self._topics = [f"{self._scope_id}:policy:."]
        # The pub/sub client for data updates
        self._client = None
        # The task running the Pub/Sub subscribing client
        self._subscriber_task = None
        self._policy_update_task = None
        self._stopping = False
        # policy fetcher - fetches policy bundles
        self._policy_fetcher = PolicyFetcher()
        # callbacks on policy changes
        self._data_fetcher = data_fetcher or DataFetcher()
        self._callbacks_register = callbacks_register or CallbacksRegister()
        self._callbacks_reporter = CallbacksReporter(self._callbacks_register)
        self._should_send_reports = (
            opal_client_config.SHOULD_REPORT_ON_DATA_UPDATES or False
        )
        # custom SSL context (for self-signed certificates)
        self._custom_ssl_context = get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context}
            if self._custom_ssl_context is not None
            else {}
        )
        self._policy_update_queue = asyncio.Queue()
        # At most ONE pending deferred bundle re-fetch, armed when a fetch
        # exhausts its retries against a retryable error (e.g. the server is
        # still cloning the scope's repo). See _maybe_schedule_deferred_refetch.
        self._deferred_refetch_task: Optional[asyncio.Task] = None
        self._deferred_refetch_rounds: int = 0
        self._tasks = TasksPool()
        self._on_connect_callbacks = on_connect or []
        self._on_disconnect_callbacks = on_disconnect or []

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if not self._stopping:
            await self.stop()

    async def _update_policy_callback(
        self, data: dict = None, topic: str = "", **kwargs
    ):
        """
        Pub/Sub callback - triggering policy updates
        will run when we get notifications on the policy topic.
        i.e: when the source repository changes (new commits)
        """
        if data is None:
            logger.warning(
                "got policy update message without data, skipping policy update!"
            )
            return

        try:
            message = PolicyUpdateMessage(**data)
        except pydantic.ValidationError as e:
            logger.warning(f"Got invalid policy update message from server: {repr(e)}")
            return

        logger.info(
            "Received policy update: topic={topic}, message={message}",
            topic=topic,
            message=message.dict(),
        )

        directories = list(
            set(message.changed_directories).intersection(
                set(self._subscription_directories)
            )
        )
        # A real policy update means the source moved on: the previous failure
        # episode is over, so the deferred round budget starts fresh. This is the
        # only *incoming* signal that resets it -- notably not a reconnect, which
        # would otherwise make MAX_DEFERRED_ROUNDS unreachable.
        self._deferred_refetch_rounds = 0
        await self.trigger_update_policy(directories)

    async def trigger_update_policy(
        self, directories: List[str] = None, force_full_update: bool = False
    ):
        # A freshly-triggered update supersedes any pending deferred re-fetch:
        # we are about to do the work that the timer was waiting to do.
        # NOTE: deliberately does NOT reset `_deferred_refetch_rounds`. This runs
        # on every WebSocket reconnect (via _on_connect), and reconnects are
        # frequent during exactly the outages the round budget is meant to bound
        # -- resetting here would make MAX_DEFERRED_ROUNDS unreachable. Only a
        # genuine incoming policy update, or a successful fetch, resets it.
        self._cancel_deferred_refetch()
        await self._policy_update_queue.put((directories, force_full_update))

    def _cancel_deferred_refetch(self) -> Optional[asyncio.Task]:
        """Cancels the pending deferred re-fetch, if any, and returns it.

        The caller may await the returned task to make sure it has
        actually finished unwinding (see stop()).
        """
        task = self._deferred_refetch_task
        if task is not None:
            self._deferred_refetch_task = None
            task.cancel()
        return task

    def _deferred_refetch_delay(
        self, retry_after: Optional[float], round_index: int
    ) -> float:
        """How long to wait before the next deferred bundle re-fetch.

        Whichever is longer: the server's `Retry-After` hint, or our own
        per-round exponential backoff (5, 10, 20, 40, ... seconds). The
        result is then bounded above by POLICY_UPDATER_MAX_RETRY_AFTER --
        so neither a hostile header nor a long outage pushes the next
        attempt hours out -- and below by DEFERRED_REFETCH_BASE_SECONDS,
        so a mis-set (or zero) ceiling cannot collapse the deferral into
        a back-to-back loop. Finally it is jittered into [delay/2, delay]
        so a whole fleet does not come back on the same tick.
        """
        ceiling = float(opal_client_config.POLICY_UPDATER_MAX_RETRY_AFTER)
        backoff = DEFERRED_REFETCH_BASE_SECONDS * (2 ** max(round_index - 1, 0))
        raw = backoff if retry_after is None else max(retry_after, backoff)
        bounded = max(min(raw, ceiling), DEFERRED_REFETCH_BASE_SECONDS)
        return _jittered(bounded)

    def _maybe_schedule_deferred_refetch(
        self,
        error: RetryableBundleError,
        directories: List[str],
        force_full_update: bool,
    ):
        """Arms a single deferred bundle re-fetch after a retryable failure.

        Without this, a client whose bundle request exhausted its
        retries sits on a stale policy store until the next pub/sub
        message or WebSocket reconnect -- which for a low-churn scope
        can be hours.
        """
        if not opal_client_config.POLICY_UPDATER_RESCHEDULE_ON_RETRYABLE:
            return

        if self._stopping:
            return

        # Coalesce: one pending timer at a time, never a stack of them.
        if self._deferred_refetch_task is not None:
            return

        max_rounds = opal_client_config.POLICY_UPDATER_MAX_DEFERRED_ROUNDS
        if self._deferred_refetch_rounds >= max_rounds:
            logger.warning(
                "Giving up on deferred bundle re-fetch after {rounds} rounds; "
                "waiting for the next policy update or reconnect",
                rounds=self._deferred_refetch_rounds,
            )
            return

        self._deferred_refetch_rounds += 1
        delay = self._deferred_refetch_delay(
            error.retry_after, self._deferred_refetch_rounds
        )
        logger.warning(
            "Deferring bundle re-fetch by {delay}s (round {round}/{max_rounds})",
            delay=delay,
            round=self._deferred_refetch_rounds,
            max_rounds=max_rounds,
        )
        self._deferred_refetch_task = asyncio.create_task(
            self._deferred_refetch(delay, directories, force_full_update)
        )

    async def _deferred_refetch(
        self, delay: float, directories: List[str], force_full_update: bool
    ):
        """Sleeps, then re-queues the update that failed.

        Goes through the update queue rather than calling
        update_policy() directly so that the re-fetch stays serialized
        with every other policy update -- two concurrent policy-store
        transactions would race.
        """
        await asyncio.sleep(delay)
        # Clear our own handle before queueing: from here on there is nothing
        # left to cancel, and the next failure is free to arm a new timer.
        self._deferred_refetch_task = None
        await self._policy_update_queue.put((directories, force_full_update))

    async def _on_connect(self, client: PubSubClient, channel: RpcChannel):
        """Pub/Sub on_connect callback On connection to backend, whether its
        the first connection, or reconnecting after downtime, refetch the state
        opa needs.

        As long as the connection is alive we know we are in sync with
        the server, when the connection is lost we assume we need to
        start from scratch.
        """
        logger.info("Connected to server")
        await self.trigger_update_policy()
        if opal_common_config.STATISTICS_ENABLED:
            await self._client.wait_until_ready()
            # publish statistics to the server about new connection from client (only if STATISTICS_ENABLED is True, default to False)
            await self._client.publish(
                [opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL],
                data={
                    "topics": self._topics,
                    "client_id": self._opal_client_id,
                    "rpc_id": channel.id,
                },
            )

    async def _on_disconnect(self, channel: RpcChannel):
        """Pub/Sub on_disconnect callback."""
        logger.info("Disconnected from server")

    def reset(self):
        """Resets internal state so the updater can be started again after
        being stopped."""
        self._stopping = False
        self._deferred_refetch_rounds = 0
        self._tasks.restart()

    async def start(self):
        """Launches the policy updater."""
        logger.info("Launching policy updater")
        await self._callbacks_reporter.start()
        if self._policy_update_task is None:
            self._policy_update_task = asyncio.create_task(self.handle_policy_updates())
        if self._subscriber_task is None:
            self._subscriber_task = asyncio.create_task(self._subscriber())
            await self._data_fetcher.start()

    async def stop(self):
        """Stops the policy updater."""
        self._stopping = True
        logger.info("Stopping policy updater")

        # drop any pending deferred bundle re-fetch, and wait for it to unwind
        # so we do not leave a half-cancelled task behind at shutdown
        deferred_refetch = self._cancel_deferred_refetch()
        if deferred_refetch is not None:
            await asyncio.gather(deferred_refetch, return_exceptions=True)

        # disconnect from Pub/Sub
        if self._client is not None:
            try:
                await asyncio.wait_for(self._client.disconnect(), timeout=3)
            except asyncio.TimeoutError:
                logger.debug(
                    "Timeout waiting for PolicyUpdater pubsub client to disconnect"
                )

        # stop subscriber task
        if self._subscriber_task is not None:
            logger.debug("Cancelling PolicyUpdater subscriber task")
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError as exc:
                logger.debug(
                    "PolicyUpdater subscriber task was force-cancelled: {exc}",
                    exc=repr(exc),
                )
            self._subscriber_task = None
            logger.debug("PolicyUpdater subscriber task was cancelled")

        await self._data_fetcher.stop()

        # stop queue handling
        if self._policy_update_task is not None:
            self._policy_update_task.cancel()
            try:
                await self._policy_update_task
            except asyncio.CancelledError:
                pass
            self._policy_update_task = None

        # stop the callbacks reporter
        await self._callbacks_reporter.stop()

        await self._tasks.shutdown()

    async def wait_until_done(self):
        if self._subscriber_task is not None:
            await self._subscriber_task

    async def _subscriber(self):
        """Coroutine meant to be spunoff with create_task to listen in the
        background for policy update events and pass them to the
        update_policy() callback (which will fetch the relevant policy bundle
        from the server and update the policy store)."""
        logger.info("Subscribing to topics: {topics}", topics=self._topics)
        self._client = PubSubClient(
            topics=self._topics,
            callback=self._update_policy_callback,
            on_connect=[self._on_connect, *self._on_connect_callbacks],
            on_disconnect=[self._on_disconnect, *self._on_disconnect_callbacks],
            additional_headers=self._extra_headers,
            keep_alive=opal_client_config.KEEP_ALIVE_INTERVAL,
            server_uri=self._server_url,
            **self._ssl_context_kwargs,
        )
        async with self._client:
            await self._client.wait_until_done()

    async def update_policy(
        self,
        directories: List[str],
        force_full_update: bool,
    ):
        """Fetches policy (code, e.g: rego) from backend and stores it in the
        policy store.

        Args:
            policy_store (BasePolicyStoreClient, optional): Policy store client to use to store policy code.
            directories (List[str], optional): specific source directories we want.
            force_full_update (bool, optional): if true, ignore stored hash and fetch full policy bundle.
        """
        directories = (
            directories
            if directories is not None
            else default_subscribed_policy_directories()
        )
        if force_full_update:
            logger.info("full update was forced (ignoring stored hash if exists)")
            base_hash = None
        else:
            try:
                base_hash = await self._policy_store.get_policy_version()
            except Exception as err:
                # The policy store can be restarting alongside the server. If we
                # let this escape, update_policy() never reaches the fetch, so no
                # deferred re-fetch is armed and the client waits for an external
                # event to recover. Degrade to a full bundle instead.
                logger.warning(
                    "Could not read the current policy version from the policy "
                    "store ({err}); falling back to a full bundle fetch",
                    err=repr(err),
                )
                base_hash = None

        if base_hash is None:
            logger.info("Refetching policy code (full bundle)")
        else:
            logger.info(
                "Refetching policy code (delta bundle), base hash: '{base_hash}'",
                base_hash=base_hash,
            )
        bundle_error = None
        bundle = None
        bundle_succeeded = True
        retryable_error: Optional[RetryableBundleError] = None
        try:
            bundle: Optional[
                PolicyBundle
            ] = await self._policy_fetcher.fetch_policy_bundle(
                directories, base_hash=base_hash
            )
            if bundle:
                if bundle.old_hash is None:
                    logger.info(
                        "Got policy bundle with {rego_files} rego files, {data_files} data files, commit hash: '{commit_hash}'",
                        rego_files=len(bundle.policy_modules),
                        data_files=len(bundle.data_modules),
                        commit_hash=bundle.hash,
                        manifest=bundle.manifest,
                    )
                else:
                    deleted_files = (
                        None
                        if bundle.deleted_files is None
                        else bundle.deleted_files.dict()
                    )
                    logger.info(
                        "got policy bundle (delta): '{diff_against_hash}' -> '{commit_hash}', manifest: {manifest}, deleted: {deleted}",
                        commit_hash=bundle.hash,
                        diff_against_hash=bundle.old_hash,
                        manifest=bundle.manifest,
                        deleted=deleted_files,
                    )
        except Exception as err:
            bundle_error = repr(err)
            bundle_succeeded = False
            if isinstance(err, RetryableBundleError):
                retryable_error = err

        if bundle_succeeded:
            # We are in sync again: drop any timer armed by an earlier failure.
            self._cancel_deferred_refetch()
            self._deferred_refetch_rounds = 0
        elif retryable_error is not None:
            self._maybe_schedule_deferred_refetch(
                retryable_error, directories, force_full_update
            )

        bundle_hash = None if bundle is None else bundle.hash

        # store policy bundle in OPA cache
        # We wrap our interaction with the policy store with a transaction, so that
        # if the write-op fails, we will mark the transaction as failed.
        async with self._policy_store.transaction_context(
            bundle_hash, transaction_type=TransactionType.policy
        ) as store_transaction:
            store_transaction._update_remote_status(
                url=self._policy_fetcher.policy_endpoint_url,
                status=bundle_succeeded,
                error=bundle_error,
            )
            if bundle:
                await store_transaction.set_policies(bundle)
                # if we got here, we did not throw during the transaction
                if self._should_send_reports:
                    # spin off reporting (no need to wait on it)
                    report = DataUpdateReport(policy_hash=bundle.hash, reports=[])
                    self._tasks.add_task(
                        self._callbacks_reporter.report_update_results(report)
                    )

    async def handle_policy_updates(self):
        while True:
            try:
                directories, force_full_update = await self._policy_update_queue.get()
                await self.update_policy(directories, force_full_update)
            except asyncio.CancelledError:
                logger.debug("PolicyUpdater policy update task was cancelled")
                break
            except Exception:
                logger.exception("Failed to update policy")

    @property
    def topics(self) -> List[str]:
        return self._topics

    @property
    def callbacks_reporter(self) -> CallbacksReporter:
        return self._callbacks_reporter
