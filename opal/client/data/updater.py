import asyncio
from opal.client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal.fetcher.events import FetcherConfig
from typing import Dict, Iterable, List
from opal.common.schemas.data import DataUpdate, DataSourceEntry
from fastapi_websocket_rpc.rpc_channel import RpcChannel
from fastapi_websocket_pubsub import PubSubClient

from opal.client.logger import get_logger
from opal.client.config import DATA_TOPICS, DATA_UPDATES_WS_URL, CLIENT_TOKEN, KEEP_ALIVE_INTERVAL
from opal.common.utils import AsyncioEventLoopThread, get_authorization_header
from opal.client.policy_store.policy_store_client_factory import DEFAULT_POLICY_STORE
from opal.client.data.fetcher import DataFetcher
from opal.client.data.rpc import TenantAwareRpcEventClientMethods


logger = get_logger("Opal Client")
updater_logger = get_logger("Data Updater")


async def update_policy_data(update: DataUpdate = None, policy_store: BasePolicyStoreClient = DEFAULT_POLICY_STORE, data_fetcher=None):
    """
    fetches policy data (policy configuration) from backend and updates it into policy-store (i.e. OPA)
    """
    if data_fetcher is None:
        data_fetcher = DataFetcher()
    # types
    urls: Dict[str, FetcherConfig] = None
    url_to_entry: Dict[str, DataSourceEntry] = None
    # if we have an actual specification for the update
    if update is not None:
        entries: List[DataSourceEntry] = update.entries
        urls = {entry.url: entry.config for entry in entries}
        url_to_entry = {entry.url: entry for entry in entries}
    # get the data for the update
    updater_logger.info("Fetching policy data", urls=urls.keys())
    policy_data_by_urls = await data_fetcher.fetch_policy_data(urls)
    # save the data from the update
    updater_logger.info("Saving fetched data to policy-store")
    for url in policy_data_by_urls:
        # get path to store the URL data (default mode (None) is as "" - i.e. as all the data at root)
        entry = url_to_entry.get(url, None)
        policy_store_path = "" if entry is None else entry.dst_path
        # None is not valid - use "" (protect from missconfig)
        if policy_store_path is None:
            policy_store_path = ""
        # fix opa_path (if not empty must start with "/" to be nested under data)
        if policy_store_path != "" and not policy_store_path.startswith("/"):
            policy_store_path = f"/{policy_store_path}"
        policy_data = policy_data_by_urls[url]
        await policy_store.set_policy_data(policy_data, path=policy_store_path)


async def refetch_policy_data_and_update_store(policy_store: BasePolicyStoreClient = DEFAULT_POLICY_STORE, data_fetcher=None):
    """
    will bring fresh data from backend, and will inject into OPA.
    """
    # TODO - this should be replaced by an update coming the server on client connect
    await update_policy_data(policy_store=policy_store, data_fetcher=data_fetcher)


class DataUpdater:
    def __init__(self, token: str = CLIENT_TOKEN, 
                 server_url: str = DATA_UPDATES_WS_URL,
                 fetch_on_connect:bool=True,
                 data_topics: List[str] = None, 
                 policy_store: BasePolicyStoreClient = DEFAULT_POLICY_STORE):
        # Should the client use the default data source to fetch on connect
        self._fetch_on_connect = fetch_on_connect
        # The policy store we'll save data updates into
        self._policy_store = policy_store
        # Pub/Sub topics we subscribe to for data updates
        self._data_topics = data_topics if data_topics is not None else DATA_TOPICS
        # The pub/sub client for data updates
        self._client = None
        # The task running the Pub/Sub subcribing client
        self._subscriber_task = None
        # Data fetcher
        self._data_fetcher = DataFetcher()
        self._token = token
        self._server_url = server_url
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """
        Context handler to terminate internal tasks
        """
        await self.stop()


    async def _update_policy_data(self, data: dict = None, topic=""):
        """
        will run when we get notifications on the policy_data topic.
        i.e: when new roles are added, changes to permissions, etc.
        """
        if data is not None:
            reason = data.get("reason", "")
        else:
            reason = "Periodic update"
        updater_logger.info("Updating policy data", reason=reason)
        update = DataUpdate.parse_obj(data)
        asyncio.create_task(update_policy_data(update, policy_store=self._policy_store, data_fetcher=self._data_fetcher))

    async def on_connect(self, client: PubSubClient, channel: RpcChannel):
        # on connection to backend, whether its the first connection
        # or reconnecting after downtime, refetch the state opa needs.
        updater_logger.info("Connected to server")
        if self._fetch_on_connect:
            await refetch_policy_data_and_update_store(policy_store=self._policy_store, data_fetcher=self._data_fetcher)

    async def on_disconnect(self, channel: RpcChannel):
        updater_logger.info("Disconnected from server")

    async def start(self):
        logger.info("Launching data updater")
        if self._subscriber_task is None:
            self._subscriber_task = asyncio.create_task(self._subscriber())
            await self._data_fetcher.start()

    async def _subscriber(self):
        """
        Coroutine meant to be spunoff with create_task to listen in the background for data events and pass them to the data_fetcher 
        """
        updater_logger.info("Subscribing to topics", topics=self._data_topics)
        self._client = PubSubClient(
            self._data_topics,
            self._update_policy_data,
            methods_class=TenantAwareRpcEventClientMethods,
            on_connect=[self.on_connect],
            extra_headers=self._extra_headers,
            keep_alive=KEEP_ALIVE_INTERVAL,
            server_uri=self._server_url
        )
        async with self._client:
            await self._client.wait_until_done()


    async def stop(self):
        logger.info("Stopping data updater")
        # disconnect from Pub/Sub
        await self._client.disconnect()
        # stop subscriber task
        self._subscriber_task.cancel()
        # stop the data fetcher
        await self._data_fetcher.stop()



