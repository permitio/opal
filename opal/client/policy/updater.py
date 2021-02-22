import asyncio

from typing import Coroutine, List, Tuple, cast

from fastapi_websocket_rpc.rpc_channel import RpcChannel

from opal.client.logger import get_logger
from opal.client.config import POLICY_UPDATES_WS_URL, CLIENT_TOKEN
from opal.client.policy.rpc import AuthenticatedPubSubClient, TenantAwareRpcEventClientMethods
from opal.client.utils import AsyncioEventLoopThread
from opal.client.policy.fetcher import policy_fetcher
from opal.client.enforcer.client import opa


logger = get_logger("Horizon")
updater_logger = get_logger("Updater")


async def update_policy(**kwargs):
    """
    fetches policy (rego) from backend and updates OPA
    """
    updater_logger.info("Refetching policy (rego)", **kwargs)
    policy = await policy_fetcher.fetch_policy()
    await opa.set_policy(policy)


async def update_policy_data(**kwargs):
    """
    fetches policy data (policy configuration) from backend and updates OPA
    """
    updater_logger.info("Refetching policy data", **kwargs)
    policy_data = await policy_fetcher.fetch_policy_data()
    await opa.set_policy_data(policy_data)


async def refetch_policy_and_update_opa(**kwargs):
    """
    will bring both rego and data from backend, and will inject into OPA.
    """
    await update_policy(**kwargs)
    await update_policy_data(**kwargs)


class PolicyUpdater:
    def __init__(self, token=CLIENT_TOKEN, server_url=POLICY_UPDATES_WS_URL):
        self._thread = AsyncioEventLoopThread(name="PolicyUpdaterThread")
        self._token = token
        self._server_url = server_url

    async def _update_policy(self, data=None, **kwargs):
        """
        will run when we get notifications on the policy topic.
        i.e: when rego changes
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        await update_policy(reason=reason, **kwargs)

    async def _update_policy_data(self, data=None, **kwargs):
        """
        will run when we get notifications on the policy_data topic.
        i.e: when new roles are added, changes to permissions, etc.
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        await update_policy_data(reason=reason, **kwargs)

    async def on_connect(self, client:AuthenticatedPubSubClient, channel:RpcChannel):
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
        self._client = AuthenticatedPubSubClient(
            self._token,
            methods_class=TenantAwareRpcEventClientMethods,
            on_connect=[self.on_connect],
            on_disconnect=[self.on_disconnect])
        updater_logger.info("Subscribing to topics", topics=['policy', 'policy_data'])
        self._client.subscribe("policy", self._update_policy)
        self._client.subscribe("policy_data", self._update_policy_data)
        self._client.start_client(f"{self._server_url}", loop=self._thread.loop)

    async def stop(self):
        logger.info("Stopping updater")
        await self._client.disconnect()
        self._thread.stop()


policy_updater = PolicyUpdater()
