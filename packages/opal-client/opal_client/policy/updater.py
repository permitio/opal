import asyncio
import hashlib
import json
from pathlib import PurePosixPath
from typing import Dict, List, Optional

import pydantic
from fastapi_websocket_pubsub import PubSubClient
from fastapi_websocket_pubsub.pub_sub_client import PubSubOnConnectCallback
from fastapi_websocket_rpc.rpc_channel import OnDisconnectCallback, RpcChannel
from opal_client.callbacks.register import CallbacksRegister
from opal_client.callbacks.reporter import CallbacksReporter
from opal_client.config import opal_client_config
from opal_client.data.fetcher import DataFetcher
from opal_client.logger import logger
from opal_client.policy.fetcher import PolicyFetcher
from opal_client.policy.topics import (
    default_subscribed_policy_directories,
    resolve_policy_source_ids,
)
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
from opal_common.topics.utils import (
    pubsub_topics_from_directories,
    pubsub_topics_from_sources,
)
from opal_common.utils import get_authorization_header


def merge_source_policy_bundles(
    source_bundles: Dict[str, PolicyBundle],
) -> PolicyBundle:
    policy_modules = []
    data_modules = []
    manifest = []
    module_paths = {}
    package_names = {}
    data_destinations = []

    for source_id in source_bundles:
        bundle = source_bundles[source_id]
        for module in bundle.policy_modules:
            previous_source = module_paths.get(module.path)
            if previous_source is not None and previous_source != source_id:
                raise ValueError(
                    f"Policy module path '{module.path}' is shared by sources "
                    f"'{previous_source}' and '{source_id}'"
                )
            module_paths[module.path] = source_id

            if module.package_name:
                previous_source = package_names.get(module.package_name)
                if previous_source is not None and previous_source != source_id:
                    raise ValueError(
                        f"Rego package '{module.package_name}' is shared by sources "
                        f"'{previous_source}' and '{source_id}'"
                    )
                package_names[module.package_name] = source_id

        for module in bundle.data_modules:
            destination = PurePosixPath(module.path)
            for previous_destination, previous_source in data_destinations:
                if previous_source != source_id and (
                    destination == previous_destination
                    or destination in previous_destination.parents
                    or previous_destination in destination.parents
                ):
                    raise ValueError(
                        f"Data destinations '{previous_destination}' and "
                        f"'{destination}' overlap between sources "
                        f"'{previous_source}' and '{source_id}'"
                    )
            data_destinations.append((destination, source_id))

        policy_modules.extend(bundle.policy_modules)
        data_modules.extend(bundle.data_modules)
        manifest.extend(bundle.manifest)

    source_hashes = {
        source_id: source_bundles[source_id].hash
        for source_id in sorted(source_bundles)
    }
    combined_hash = hashlib.sha256(
        json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return PolicyBundle(
        manifest=list(dict.fromkeys(manifest)),
        hash=combined_hash,
        old_hash=None,
        data_modules=data_modules,
        policy_modules=policy_modules,
    )


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
        self._source_ids = resolve_policy_source_ids(
            opal_client_config.POLICY_SOURCE_ID,
            opal_client_config.POLICY_SOURCE_IDS,
        )
        self._multi_source = len(self._source_ids) > 1
        if self._multi_source and self._scope_id != "default":
            raise ValueError(
                "POLICY_SOURCE_IDS is not supported with OPAL_SCOPE_ID; use default policy mode"
            )
        self._source_bundles: Dict[str, PolicyBundle] = {}
        self._source_hashes: Dict[str, str] = {}

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
            if self._source_ids:
                self._topics = pubsub_topics_from_sources(
                    self._subscription_directories, self._source_ids
                )
            else:
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
        self._policy_fetcher = PolicyFetcher(
            source_id=self._source_ids[0] if len(self._source_ids) == 1 else None
        )
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
        self._multi_source_retry_task = None
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
            message=message.model_dump(),
        )

        if self._source_ids and message.source_id not in self._source_ids:
            logger.warning(
                "Ignoring policy update for unselected source {source_id}; selected sources are {configured_source_ids}",
                source_id=message.source_id,
                configured_source_ids=self._source_ids,
            )
            return

        directories = list(
            set(message.changed_directories).intersection(
                set(self._subscription_directories)
            )
        )
        await self.trigger_update_policy(directories, source_id=message.source_id)

    async def trigger_update_policy(
        self,
        directories: List[str] = None,
        force_full_update: bool = False,
        source_id: Optional[str] = None,
    ):
        await self._policy_update_queue.put((directories, force_full_update, source_id))

    async def _on_connect(self, client: PubSubClient, channel: RpcChannel):
        """Pub/Sub on_connect callback On connection to backend, whether its
        the first connection, or reconnecting after downtime, refetch the state
        opa needs.

        As long as the connection is alive we know we are in sync with
        the server, when the connection is lost we assume we need to
        start from scratch.
        """
        logger.info("Connected to server")
        await self.trigger_update_policy(force_full_update=self._multi_source)
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

        if self._multi_source_retry_task is not None:
            self._multi_source_retry_task.cancel()
            try:
                await self._multi_source_retry_task
            except asyncio.CancelledError:
                pass
            self._multi_source_retry_task = None

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
        source_id: Optional[str] = None,
    ):
        """Fetches policy (code, e.g: rego) from backend and stores it in the
        policy store.

        Args:
            policy_store (BasePolicyStoreClient, optional): Policy store client to use to store policy code.
            directories (List[str], optional): specific source directories we want.
            force_full_update (bool, optional): if true, ignore stored hash and fetch full policy bundle.
        """
        if self._multi_source:
            return await self._update_multiple_source_policies(
                directories, force_full_update, source_id
            )

        directories = (
            directories
            if directories is not None
            else default_subscribed_policy_directories()
        )
        if force_full_update:
            logger.info("full update was forced (ignoring stored hash if exists)")
            base_hash = None
        else:
            base_hash = await self._policy_store.get_policy_version()

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
        try:
            bundle: Optional[
                PolicyBundle
            ] = await self._policy_fetcher.fetch_policy_bundle(
                directories, base_hash=base_hash, source_id=source_id
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
                        else bundle.deleted_files.model_dump()
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

    async def _update_multiple_source_policies(
        self,
        directories: Optional[List[str]],
        force_full_update: bool,
        source_id: Optional[str],
    ):
        directories = default_subscribed_policy_directories(
            self._subscription_directories
        )
        if source_id is not None and source_id not in self._source_ids:
            logger.warning(
                "Ignoring update for unselected policy source {source_id}",
                source_id=source_id,
            )
            return

        source_ids = (
            self._source_ids if force_full_update or source_id is None else [source_id]
        )
        updated_bundles = {}
        source_errors = {}
        for current_source_id in source_ids:
            try:
                bundle = await self._policy_fetcher.fetch_policy_bundle(
                    directories,
                    base_hash=None,
                    source_id=current_source_id,
                )
            except Exception as exc:
                source_errors[current_source_id] = repr(exc)
                logger.exception(
                    "Failed to fetch policy source {source_id}",
                    source_id=current_source_id,
                )
                continue
            if bundle is not None:
                updated_bundles[current_source_id] = bundle

        if not updated_bundles:
            self._schedule_multi_source_retry()
            return

        available_bundles = {**self._source_bundles, **updated_bundles}
        candidate_bundles = {
            current_source_id: available_bundles[current_source_id]
            for current_source_id in self._source_ids
            if current_source_id in available_bundles
        }
        missing_sources = set(self._source_ids).difference(candidate_bundles)
        if missing_sources:
            logger.warning(
                "Skipping aggregate policy update until every selected source has a full snapshot; missing: {source_ids}",
                source_ids=sorted(missing_sources),
            )
            self._schedule_multi_source_retry()
            return

        try:
            aggregate_bundle = merge_source_policy_bundles(candidate_bundles)
        except ValueError as exc:
            logger.error(
                "Rejecting conflicting policy sources: {error}", error=str(exc)
            )
            return

        bundle_succeeded = True
        bundle_error = None
        try:
            async with self._policy_store.transaction_context(
                aggregate_bundle.hash, transaction_type=TransactionType.policy
            ) as store_transaction:
                for current_source_id in source_ids:
                    store_transaction._update_remote_status(
                        url=(
                            f"{self._policy_fetcher.policy_endpoint_url}"
                            f"?source_id={current_source_id}"
                        ),
                        status=current_source_id not in source_errors,
                        error=source_errors.get(current_source_id),
                    )
                await store_transaction.set_policies(aggregate_bundle)
        except Exception:
            logger.exception("Failed to apply aggregate policy bundle")
            self._schedule_multi_source_retry()
            return

        self._source_bundles = candidate_bundles
        self._source_hashes.update(
            {
                current_source_id: bundle.hash
                for current_source_id, bundle in updated_bundles.items()
            }
        )
        if source_errors:
            self._schedule_multi_source_retry()
        if self._should_send_reports:
            report = DataUpdateReport(policy_hash=aggregate_bundle.hash, reports=[])
            self._tasks.add_task(self._callbacks_reporter.report_update_results(report))

    def _schedule_multi_source_retry(self):
        if self._stopping:
            return
        if (
            self._multi_source_retry_task is None
            or self._multi_source_retry_task.done()
        ):
            self._multi_source_retry_task = asyncio.create_task(
                self._retry_multi_source_refresh()
            )

    async def _retry_multi_source_refresh(self):
        try:
            await asyncio.sleep(5)
            if not self._stopping:
                await self.trigger_update_policy(force_full_update=True)
        except asyncio.CancelledError:
            raise

    async def handle_policy_updates(self):
        while True:
            try:
                (
                    directories,
                    force_full_update,
                    source_id,
                ) = await self._policy_update_queue.get()
                await self.update_policy(directories, force_full_update, source_id)
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
