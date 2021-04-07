import asyncio
from aiohttp.client import ClientSession

from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_common.fetcher.events import FetcherConfig
from typing import Dict, List
from opal_common.schemas.data import DataSourceConfig, DataUpdate, DataSourceEntry
from fastapi_websocket_rpc.rpc_channel import RpcChannel
from fastapi_websocket_pubsub import PubSubClient

from opal_client.logger import logger
from opal_client.config import opal_client_config
from opal_common.utils import get_authorization_header
from opal_client.policy_store.policy_store_client_factory import DEFAULT_POLICY_STORE_GETTER
from opal_client.data.fetcher import DataFetcher
from opal_client.data.rpc import TenantAwareRpcEventClientMethods


async def update_policy_data(update: DataUpdate = None, policy_store: BasePolicyStoreClient = None, data_fetcher=None):
    """
    fetches policy data (policy configuration) from backend and updates it into policy-store (i.e. OPA)
    """
    policy_store = policy_store or DEFAULT_POLICY_STORE_GETTER()
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
    logger.info("Fetching policy data", urls=urls)
    # Urls may be None - fetch_policy_data has a default for None
    policy_data_by_urls = await data_fetcher.fetch_policy_data(urls)
    # save the data from the update
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
        logger.info(
            "Saving fetched data to policy-store: source url='{url}', destination path='{path}'",
            url=url,
            path=policy_store_path or '/'
        )
        await policy_store.set_policy_data(policy_data, path=policy_store_path)


class DataUpdater:
    def __init__(self, token: str = None,
                 pubsub_url: str = None,
                 data_sources_config_url: str = None,
                 fetch_on_connect:bool=True,
                 data_topics: List[str] = None,
                 policy_store: BasePolicyStoreClient = None):
        """
        Keeps policy-stores (e.g. OPA) up to date with relevant data
        Obtains data configuration on startup from OPAL-server
        Uses Pub/Sub to subscribe to data update events, and fetches (using FetchingEngine) data from sources.

        Args:
            token (str, optional): Auth token to include in connections to OPAL server. Defaults to CLIENT_TOKEN.
            pubsub_url (str, optional): URL for Pub/Sub updates for data. Defaults to OPAL_SERVER_PUBSUB_URL.
            data_sources_config_url (str, optional): URL to retrive base data configuration. Defaults to DEFAULT_DATA_SOURCES_CONFIG_URL.
            fetch_on_connect (bool, optional): Should the update fetch basic data immediately upon connection/reconnection. Defaults to True.
            data_topics (List[str], optional): Topics of data to fetch and subscribe to. Defaults to DATA_TOPICS.
            policy_store (BasePolicyStoreClient, optional): Policy store client to use to store data. Defaults to DEFAULT_POLICY_STORE.
        """
        # Defaults
        token: str = token or opal_client_config.CLIENT_TOKEN
        pubsub_url: str = pubsub_url or opal_client_config.SERVER_PUBSUB_URL
        data_sources_config_url: str = data_sources_config_url or opal_client_config.DEFAULT_DATA_SOURCES_CONFIG_URL        
        # Should the client use the default data source to fetch on connect
        self._fetch_on_connect = fetch_on_connect
        # The policy store we'll save data updates into
        self._policy_store = policy_store or DEFAULT_POLICY_STORE_GETTER()
        # Pub/Sub topics we subscribe to for data updates
        self._data_topics = data_topics if data_topics is not None else opal_client_config.DATA_TOPICS
        # The pub/sub client for data updates
        self._client = None
        # The task running the Pub/Sub subcribing client
        self._subscriber_task = None
        # Data fetcher
        self._data_fetcher = DataFetcher()
        self._token = token
        self._server_url = pubsub_url
        self._data_sources_config_url = data_sources_config_url
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]
        self._stopping = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """
        Context handler to terminate internal tasks
        """
        if not self._stopping:
            await self.stop()

    async def _update_policy_data_callback(self, data: dict = None, topic=""):
        """
        Pub/Sub callback - triggering data updates
        will run when we get notifications on the policy_data topic.
        i.e: when new roles are added, changes to permissions, etc.
        """
        if data is not None:
            reason = data.get("reason", "")
        else:
            reason = "Periodic update"
        logger.info("Updating policy data, reason: {reason}", reason=reason)
        update = DataUpdate.parse_obj(data)
        self.trigger_data_update(update)

    def trigger_data_update(self, update:DataUpdate):
        logger.info("Triggering data fetch and update", update=update)
        asyncio.create_task(update_policy_data(update, policy_store=self._policy_store, data_fetcher=self._data_fetcher))

    async def get_policy_data_config(self, url:str=None)->DataSourceConfig:
        """
        Get the configuration for
        Args:
            url: the URL to query for the config, Defaults to self._data_sources_config_url
        Returns:
            DataSourceConfig: the data sources config
        """
        if url is None:
            url = self._data_sources_config_url
        logger.info("Getting data-sources configuration from '{source}'", source=url)
        try:
            async with ClientSession(headers=self._extra_headers) as session:
                res = await session.get(url)
            return DataSourceConfig.parse_obj(await res.json())
        except:
            logger.exception(f"Failed to load data sources config")
            raise


    async def get_base_policy_data(self, config_url:str=None, data_fetch_reason="Initial load"):
        """
        Load data into the policy store according to the data source's config provided in the config URL

        Args:
            config_url (str, optional): URL to retrive data sources config from. Defaults to None ( self._data_sources_config_url).
            data_fetch_reason (str, optional): Reason to log for the update operation. Defaults to "Initial load".
        """
        logger.info("Performing data configuration, reason: {reason}", reason={data_fetch_reason})
        sources_config = await self.get_policy_data_config(url=config_url)
        # translate config to a data update
        entries = sources_config.entries
        update = DataUpdate(reason=data_fetch_reason, entries=entries)
        self.trigger_data_update(update)


    async def on_connect(self, client: PubSubClient, channel: RpcChannel):
        """
        Pub/Sub on_connect callback
        On connection to backend, whether its the first connection,
        or reconnecting after downtime, refetch the state opa needs.
        As long as the connection is alive we know we are in sync with the server,
        when the connection is lost we assume we need to start from scratch.
        """
        logger.info("Connected to server")
        if self._fetch_on_connect:
            await self.get_base_policy_data()

    async def on_disconnect(self, channel: RpcChannel):
        logger.info("Disconnected from server")

    async def start(self):
        logger.info("Launching data updater")
        if self._subscriber_task is None:
            self._subscriber_task = asyncio.create_task(self._subscriber())
            await self._data_fetcher.start()

    async def _subscriber(self):
        """
        Coroutine meant to be spunoff with create_task to listen in
        the background for data events and pass them to the data_fetcher
        """
        logger.info("Subscribing to topics: {topics}", topics=self._data_topics)
        self._client = PubSubClient(
            self._data_topics,
            self._update_policy_data_callback,
            methods_class=TenantAwareRpcEventClientMethods,
            on_connect=[self.on_connect],
            extra_headers=self._extra_headers,
            keep_alive=opal_client_config.KEEP_ALIVE_INTERVAL,
            server_uri=self._server_url
        )
        async with self._client:
            await self._client.wait_until_done()

    async def stop(self):
        self._stopping = True
        logger.info("Stopping data updater")

        # disconnect from Pub/Sub
        try:
            await asyncio.wait_for(self._client.disconnect(), timeout=3)
        except asyncio.TimeoutError:
            logger.debug("Timeout waiting for DataUpdater pubsub client to disconnect")

        # stop subscriber task
        if self._subscriber_task is not None:
            logger.debug("Cancelling DataUpdater subscriber task")
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError as exc:
                logger.debug("DataUpdater subscriber task was force-cancelled: {e}", exc=exc)
            self._subscriber_task = None
            logger.debug("DataUpdater subscriber task was cancelled")

        # stop the data fetcher
        logger.debug("Stopping data fetcher")
        await self._data_fetcher.stop()

    async def wait_until_done(self):
        if self._subscriber_task is not None:
            await self._subscriber_task



