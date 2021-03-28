import asyncio
from typing import List, Optional

from fastapi_websocket_rpc.rpc_channel import RpcChannel
from fastapi_websocket_pubsub import PubSubClient

from opal.common.utils import get_authorization_header
from opal.common.schemas.policy import PolicyBundle
from opal.common.topics.utils import (
    pubsub_topics_from_directories,
    POLICY_PREFIX,
    remove_prefix
)
from opal.client.logger import logger
from opal.config.client.config import POLICY_SUBSCRIPTION_DIRS, OPAL_SERVER_PUBSUB_URL, CLIENT_TOKEN, KEEP_ALIVE_INTERVAL
from opal.client.policy.fetcher import policy_fetcher
from opal.client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal.client.policy_store.policy_store_client_factory import DEFAULT_POLICY_STORE
from opal.client.policy.topics import default_subscribed_policy_directories


async def update_policy(policy_store: BasePolicyStoreClient, directories: List[str] = None, force_full_update=False):
    """
    fetches policy (code, e.g: rego) from backend and stores it in the policy store.

    Args:
        policy_store (BasePolicyStoreClient, optional): Policy store client to use to store policy code.
        directories (List[str], optional): specific source directories we want.
        force_full_update (bool, optional): if true, ignore stored hash and fetch full policy bundle.
    """
    directories = directories if directories is not None else default_subscribed_policy_directories()
    if force_full_update:
        logger.info("full update was forced (ignoring stored hash if exists)")
        base_hash = None
    else:
        base_hash = await policy_store.get_policy_version()

    if base_hash is None:
        logger.info("Refetching policy code (full bundle)")
    else:
        logger.info("Refetching policy code (delta bundle), base hash: '{base_hash}'", base_hash=base_hash)
    bundle: Optional[PolicyBundle] = await policy_fetcher.fetch_policy_bundle(directories, base_hash=base_hash)
    if bundle:
        if bundle.old_hash is None:
            logger.info(
                "got policy bundle, commit hash: '{commit_hash}'",
                commit_hash=bundle.hash,
                manifest=bundle.manifest
            )
        else:
            deleted_files = None if bundle.deleted_files is None else bundle.deleted_files.dict()
            logger.info(
                "got policy bundle (delta): '{diff_against_hash}' -> '{commit_hash}'",
                commit_hash=bundle.hash,
                diff_against_hash=bundle.old_hash,
                manifest=bundle.manifest,
                deleted=deleted_files
            )
        await policy_store.set_policies(bundle)


class PolicyUpdater:
    """
    Keeps policy-stores (e.g. OPA) up to date with relevant policy code
    (e.g: rego) and static data (e.g: data.json files like in OPA bundles).

    Uses Pub/Sub to subscribe to specific directories in the policy code
    repository (i.e: git), and fetches bundles containing updated policy code.
    """
    def __init__(
        self,
        token: str = CLIENT_TOKEN,
        pubsub_url: str = OPAL_SERVER_PUBSUB_URL,
        subscription_directories: List[str] = POLICY_SUBSCRIPTION_DIRS,
        policy_store: BasePolicyStoreClient = DEFAULT_POLICY_STORE,
    ):
        """inits the policy updater.

        Args:
            token (str, optional): Auth token to include in connections to OPAL server. Defaults to CLIENT_TOKEN.
            pubsub_url (str, optional): URL for Pub/Sub updates for policy. Defaults to OPAL_SERVER_PUBSUB_URL.
            subscription_directories (List[str], optional): directories in the policy source repo to subscribe to.
                Defaults to POLICY_SUBSCRIPTION_DIRS. every time the directory is updated by a commit we will receive
                a message on its respective topic. we dedups directories with ancestral relation, and will only
                receive one message for each updated file.
            policy_store (BasePolicyStoreClient, optional): Policy store client to use to store policy code. Defaults to DEFAULT_POLICY_STORE.
        """
        # The policy store we'll save policy modules into (i.e: OPA)
        self._policy_store = policy_store
        # pub/sub server url and authentication data
        self._server_url = pubsub_url
        self._token = token
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]
        # Pub/Sub topics we subscribe to for policy updates
        self._topics = pubsub_topics_from_directories(subscription_directories)
        # The pub/sub client for data updates
        self._client = None
        # The task running the Pub/Sub subcribing client
        self._subscriber_task = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def _update_policy_callback(self, data: dict = None, topic: str = "", **kwargs):
        """
        Pub/Sub callback - triggering policy updates
        will run when we get notifications on the policy topic.
        i.e: when the source repository changes (new commits)
        """
        if topic.startswith(POLICY_PREFIX):
            directories = [remove_prefix(topic, prefix=POLICY_PREFIX)]
            logger.info(
                "Received policy update: affected directories={directories}, new commit hash='{new_hash}'",
                directories=directories,
                topic=topic,
                new_hash=data
            )
        else:
            directories = default_subscribed_policy_directories()
            logger.warning("Received policy updated (invalid topic): {topic}", topic=topic)

        await update_policy(self._policy_store, directories)

    async def _on_connect(self, client: PubSubClient, channel: RpcChannel):
        """
        Pub/Sub on_connect callback
        On connection to backend, whether its the first connection,
        or reconnecting after downtime, refetch the state opa needs.
        As long as the connection is alive we know we are in sync with the server,
        when the connection is lost we assume we need to start from scratch.
        """
        logger.info("Connected to server")
        await update_policy(policy_store=self._policy_store)

    async def _on_disconnect(self, channel: RpcChannel):
        """
        Pub/Sub on_disconnect callback
        """
        logger.info("Disconnected from server")

    async def start(self):
        """
        launches the policy updater
        """
        logger.info("Launching policy updater")
        if self._subscriber_task is None:
            self._subscriber_task = asyncio.create_task(self._subscriber())

    async def stop(self):
        """
        stops the policy updater
        """
        # disconnect from Pub/Sub
        await self._client.disconnect()
        # stop subscriber task
        if self._subscriber_task is not None:
            logger.info("Stopping policy updater")
            self._subscriber_task.cancel()
            await self._subscriber_task
            self._subscriber_task = None

    async def wait_until_done(self):
        if self._subscriber_task is not None:
            await self._subscriber_task

    async def _subscriber(self):
        """
        Coroutine meant to be spunoff with create_task to listen in
        the background for policy update events and pass them to the
        update_policy() callback (which will fetch the relevant policy
        bundle from the server and update the policy store).
        """
        logger.info("Subscribing to topics: {topics}", topics=self._topics)
        self._client = PubSubClient(
            topics=self._topics,
            callback=self._update_policy_callback,
            on_connect=[self._on_connect],
            on_disconnect=[self._on_disconnect],
            extra_headers=self._extra_headers,
            keep_alive=KEEP_ALIVE_INTERVAL,
            server_uri=self._server_url
        )
        async with self._client:
            await self._client.wait_until_done()