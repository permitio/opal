from typing import List
from pathlib import Path

from fastapi_websocket_rpc.rpc_channel import RpcChannel
from fastapi_websocket_pubsub import PubSubClient

from opal.client.logger import get_logger
from opal.client.config import POLICY_SUBSCRIPTION_DIRS, POLICY_UPDATES_WS_URL, CLIENT_TOKEN, KEEP_ALIVE_INTERVAL
from opal.client.utils import AsyncioEventLoopThread, get_authorization_header
from opal.client.policy.fetcher import policy_fetcher
from opal.client.enforcer.client import opa
from opal.client.policy.topics import dirs_to_topics, all_policy_directories, POLICY_PREFIX


logger = get_logger("Horizon")
updater_logger = get_logger("Policy Updater")


async def update_policy(directories: List[str] = [], **kwargs):
    """
    fetches policy (rego) from backend and updates OPA
    """
    directories = directories if directories else all_policy_directories()
    updater_logger.info("Refetching policy (rego)", **kwargs)
    bundle = await policy_fetcher.fetch_policy_bundle(directories)
    logger.info("got bundle", bundle=bundle.dict())
    await opa.set_policies(bundle)

async def refetch_policy_and_update_opa(**kwargs):
    """
    will bring both rego and data from backend, and will inject into OPA.
    """
    await update_policy(**kwargs)

class PolicyUpdater:
    def __init__(self, token=CLIENT_TOKEN, server_url=POLICY_UPDATES_WS_URL, dirs: List[str] = POLICY_SUBSCRIPTION_DIRS):
        self._thread = AsyncioEventLoopThread(name="PolicyUpdaterThread")
        self._token = token
        self._server_url = server_url
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]
        self._topics = dirs_to_topics(dirs)

    async def _update_policy(self, data=None, topic: str = "", **kwargs):
        """
        will run when we get notifications on the policy topic.
        i.e: when rego changes
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        if topic.startswith(POLICY_PREFIX):
            directories = [topic.lstrip(POLICY_PREFIX)]
        else:
            logger.warn("invalid policy topic", topic=topic)
            directories = all_policy_directories()
        await update_policy(directories, reason=reason, **kwargs)

    async def on_connect(self, client:PubSubClient, channel:RpcChannel):
        # on connection to backend, whether its the first connection
        # or reconnecting after downtime, refetch the state opa needs.
        updater_logger.info("Connected to server")
        await refetch_policy_and_update_opa()

    async def on_disconnect(self, channel:RpcChannel):
        updater_logger.info("Disconnected from server")

    def start(self):
        logger.info("Launching updater")
        self._thread.create_task(self._run_client())
        self._thread.start()

    async def _run_client(self):
        self._client = PubSubClient(
            self._token,
            on_connect=[self.on_connect],
            on_disconnect=[self.on_disconnect],
            extra_headers=self._extra_headers,
            keep_alive=KEEP_ALIVE_INTERVAL
        )
        updater_logger.info("Subscribing to topics", topics=self._topics)
        for topic in self._topics:
            self._client.subscribe(topic, self._update_policy)
        self._client.start_client(f"{self._server_url}", loop=self._thread.loop)

    async def stop(self):
        logger.info("Stopping policy updater")
        await self._client.disconnect()
        self._thread.stop()


policy_updater = PolicyUpdater()
