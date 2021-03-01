from opal.fetcher.events import FetcherConfig
from typing import Dict, List
from opal.common.schemas.data import DataUpdate, DataUpdateEntry
from fastapi_websocket_rpc.rpc_channel import RpcChannel
from fastapi_websocket_pubsub import PubSubClient

from opal.client.logger import get_logger
from opal.client.config import DATA_TOPICS, DATA_UPDATES_WS_URL, CLIENT_TOKEN, KEEP_ALIVE_INTERVAL
from opal.client.utils import AsyncioEventLoopThread, get_authorization_header
from opal.client.enforcer.policy_store.opa_client import opa
from opal.client.data.fetcher import data_fetcher
from opal.client.data.rpc import TenantAwareRpcEventClientMethods


logger = get_logger("Opal Client")
updater_logger = get_logger("Data Updater")


async def update_policy_data(update:DataUpdate=None):
    """
    fetches policy data (policy configuration) from backend and updates it into policy-store (i.e. OPA)
    """
    # types
    urls: Dict[str, FetcherConfig] = None
    url_to_entry: Dict[str, DataUpdateEntry] = None
    # if we have an actual specification for the update 
    if update is not None:
        entries: List[DataUpdateEntry] = update.entries
        urls = {entry.url : entry.config for entry in entries}
        url_to_entry = {entry.url : entry for entry in entries}
    # get the data for the update
    updater_logger.info("Fetching policy data", urls=urls.keys())
    policy_data_by_urls = await data_fetcher.fetch_policy_data(urls)
    # save the data from the update
    updater_logger.info("Saving fetched data to policy-store")
    for url in policy_data_by_urls:
        # get path to store the URL data (default mode (None) is as "" - i.e. as all the data at root)
        entry = url_to_entry.get(url, None)
        opa_path = "" if entry is None  else entry.dst_path
        # None is not valid - use "" (protect from missconfig)
        if opa_path is None:
            opa_path = ""
        # fix opa_path (if not empty must start with "/" to be nested under data)
        if opa_path != "" and not opa_path.startswith("/"):
            opa_path = f"/{opa_path}"
        policy_data = policy_data_by_urls[url]
        opa.set_policy_data(policy_data, path=opa_path)


async def refetch_policy_data_and_update_store(**kwargs):
    """
    will bring fresh data from backend, and will inject into OPA.
    """
    # TODO - this should be replaced by an update coming the server on client connect
    await update_policy_data(**kwargs)

class DataUpdater:
    def __init__(self, token=CLIENT_TOKEN, server_url=DATA_UPDATES_WS_URL, data_topics=None):
        self._data_topics = DATA_TOPICS
        if data_topics is not None:
            self._data_topics.extend(data_topics)
        self._thread = AsyncioEventLoopThread(name="PolicyUpdaterThread")
        self._token = token
        self._server_url = server_url
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]

    async def _update_policy_data(self, update:DataUpdate=None):
        """
        will run when we get notifications on the policy_data topic.
        i.e: when new roles are added, changes to permissions, etc.
        """
        if update is not None:
            reason = update.reason
        else:
            reason = "Periodic update"
        updater_logger.info("Updating policy data", reason=reason)

        await update_policy_data(update)

    async def on_connect(self, client:PubSubClient, channel:RpcChannel):
        # on connection to backend, whether its the first connection
        # or reconnecting after downtime, refetch the state opa needs.
        updater_logger.info("Connected to server")
        await refetch_policy_data_and_update_store()

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
        self._subscribe_for_updates()
        self._client.start_client(f"{self._server_url}", loop=self._thread.loop)

    def _subscribe_for_updates(self):
        updater_logger.info("Subscribing to topics", topics=self._data_topics)
        for topic in self._data_topics:
            self._client.subscribe(topic, self._update_policy_data)

    async def stop(self):
        logger.info("Stopping data updater")
        await self._client.disconnect()
        # stop the data fetcher singleton 
        await data_fetcher.stop()
        self._thread.stop()


data_updater = DataUpdater()
