from fastapi_websocket_rpc.rpc_channel import RpcChannel
from fastapi_websocket_pubsub import PubSubClient

from horizon.logger import get_logger
from horizon.config import DATA_UPDATES_WS_URL, CLIENT_TOKEN, KEEP_ALIVE_INTERVAL
from horizon.utils import AsyncioEventLoopThread, get_authorization_header
from horizon.enforcer.client import opa
from horizon.data.fetcher import data_fetcher
from horizon.data.rpc import TenantAwareRpcEventClientMethods


logger = get_logger("Horizon")
updater_logger = get_logger("Data Updater")


async def update_policy_data(**kwargs):
    """
    fetches policy data (policy configuration) from backend and updates OPA
    """
    updater_logger.info("Refetching policy data", **kwargs)
    policy_data = await data_fetcher.fetch_policy_data()
    await opa.set_policy_data(policy_data)


async def refetch_policy_data_and_update_opa(**kwargs):
    """
    will bring fresh data from backend, and will inject into OPA.
    """
    await update_policy_data(**kwargs)


class DataUpdater:
    def __init__(self, token=CLIENT_TOKEN, server_url=DATA_UPDATES_WS_URL):
        self._thread = AsyncioEventLoopThread(name="PolicyUpdaterThread")
        self._token = token
        self._server_url = server_url
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]

    async def _update_policy_data(self, data=None, **kwargs):
        """
        will run when we get notifications on the policy_data topic.
        i.e: when new roles are added, changes to permissions, etc.
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        await update_policy_data(reason=reason, **kwargs)

    async def on_connect(self, client:PubSubClient, channel:RpcChannel):
        # on connection to backend, whether its the first connection
        # or reconnecting after downtime, refetch the state opa needs.
        updater_logger.info("Connected to server")
        await refetch_policy_data_and_update_opa()

    async def on_disconnect(self, channel:RpcChannel):
        updater_logger.info("Disconnected from server")

    def start(self):
        logger.info("Launching updater")
        self._thread.create_task(self._run_client())
        self._thread.start()

    async def _run_client(self):
        logger.info("Launching data updater")
        self._client = PubSubClient(
            self._token,
            methods_class=TenantAwareRpcEventClientMethods,
            on_connect=[self.on_connect],
            extra_headers=self._extra_headers,
            keep_alive=KEEP_ALIVE_INTERVAL
        )
        updater_logger.info("Subscribing to topics", topics=['policy_data'])
        self._client.subscribe("policy_data", self._update_policy_data)
        self._client.start_client(f"{self._server_url}", loop=self._thread.loop)

    async def stop(self):
        logger.info("Stopping data updater")
        await self._client.disconnect()
        self._thread.stop()


data_updater = DataUpdater()
