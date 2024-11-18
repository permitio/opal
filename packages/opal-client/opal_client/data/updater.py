import asyncio
import hashlib
import itertools
import json
import uuid
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp.client import ClientError, ClientSession
from fastapi_websocket_pubsub import PubSubClient
from fastapi_websocket_pubsub.pub_sub_client import PubSubOnConnectCallback
from fastapi_websocket_rpc.rpc_channel import OnDisconnectCallback, RpcChannel
from opal_client.callbacks.register import CallbacksRegister
from opal_client.callbacks.reporter import CallbacksReporter
from opal_client.config import opal_client_config
from opal_client.data.fetcher import DataFetcher
from opal_client.data.rpc import TenantAwareRpcEventClientMethods
from opal_client.logger import logger
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_client.policy_store.policy_store_client_factory import (
    DEFAULT_POLICY_STORE_GETTER,
)
from opal_common.async_utils import TakeANumberQueue, TasksPool, repeated_call
from opal_common.config import opal_common_config
from opal_common.fetcher.events import FetcherConfig
from opal_common.http_utils import is_http_error_response
from opal_common.schemas.data import (
    DataEntryReport,
    DataSourceConfig,
    DataSourceEntry,
    DataUpdate,
    DataUpdateReport,
)
from opal_common.schemas.store import TransactionType
from opal_common.security.sslcontext import get_custom_ssl_context
from opal_common.utils import get_authorization_header
from pydantic.json import pydantic_encoder


class DataUpdater:
    def __init__(
        self,
        token: str = None,
        pubsub_url: str = None,
        data_sources_config_url: str = None,
        fetch_on_connect: bool = True,
        data_topics: List[str] = None,
        policy_store: BasePolicyStoreClient = None,
        should_send_reports=None,
        data_fetcher: Optional[DataFetcher] = None,
        callbacks_register: Optional[CallbacksRegister] = None,
        opal_client_id: str = None,
        shard_id: Optional[str] = None,
        on_connect: List[PubSubOnConnectCallback] = None,
        on_disconnect: List[OnDisconnectCallback] = None,
    ):
        """Keeps policy-stores (e.g. OPA) up to date with relevant data Obtains
        data configuration on startup from OPAL-server Uses Pub/Sub to
        subscribe to data update events, and fetches (using FetchingEngine)
        data from sources.

        Args:
            token (str, optional): Auth token to include in connections to OPAL server. Defaults to CLIENT_TOKEN.
            pubsub_url (str, optional): URL for Pub/Sub updates for data. Defaults to OPAL_SERVER_PUBSUB_URL.
            data_sources_config_url (str, optional): URL to retrieve base data configuration. Defaults to DEFAULT_DATA_SOURCES_CONFIG_URL.
            fetch_on_connect (bool, optional): Should the update fetch basic data immediately upon connection/reconnection. Defaults to True.
            data_topics (List[str], optional): Topics of data to fetch and subscribe to. Defaults to DATA_TOPICS.
            policy_store (BasePolicyStoreClient, optional): Policy store client to use to store data. Defaults to DEFAULT_POLICY_STORE.
        """
        # Defaults
        token: str = token or opal_client_config.CLIENT_TOKEN
        pubsub_url: str = pubsub_url or opal_client_config.SERVER_PUBSUB_URL
        self._scope_id = opal_client_config.SCOPE_ID
        self._data_topics = (
            data_topics if data_topics is not None else opal_client_config.DATA_TOPICS
        )

        if self._scope_id == "default":
            data_sources_config_url: str = (
                data_sources_config_url
                or opal_client_config.DEFAULT_DATA_SOURCES_CONFIG_URL
            )
        else:
            data_sources_config_url = (
                f"{opal_client_config.SERVER_URL}/scopes/{self._scope_id}/data"
            )
            self._data_topics = [
                f"{self._scope_id}:data:{topic}" for topic in self._data_topics
            ]

        # Should the client use the default data source to fetch on connect
        self._fetch_on_connect = fetch_on_connect
        # The policy store we'll save data updates into
        self._policy_store = policy_store or DEFAULT_POLICY_STORE_GETTER()

        self._should_send_reports = (
            should_send_reports
            if should_send_reports is not None
            else opal_client_config.SHOULD_REPORT_ON_DATA_UPDATES
        )
        # The pub/sub client for data updates
        self._client = None
        # The task running the Pub/Sub subscribing client
        self._subscriber_task = None
        # Data fetcher
        self._data_fetcher = data_fetcher or DataFetcher()
        self._callbacks_register = callbacks_register or CallbacksRegister()
        self._callbacks_reporter = CallbacksReporter(
            self._callbacks_register,
        )
        self._token = token
        self._shard_id = shard_id
        self._server_url = pubsub_url
        self._data_sources_config_url = data_sources_config_url
        self._opal_client_id = opal_client_id
        self._extra_headers = []
        if self._token is not None:
            self._extra_headers.append(get_authorization_header(self._token))
        if self._shard_id is not None:
            self._extra_headers.append(("X-Shard-ID", self._shard_id))
        if len(self._extra_headers) == 0:
            self._extra_headers = None
        self._stopping = False
        # custom SSL context (for self-signed certificates)
        self._custom_ssl_context = get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context}
            if self._custom_ssl_context is not None
            else {}
        )
        self._updates_storing_queue = TakeANumberQueue(logger)
        self._tasks = TasksPool()
        self._polling_update_tasks = []
        self._on_connect_callbacks = on_connect or []
        self._on_disconnect_callbacks = on_disconnect or []

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Context handler to terminate internal tasks."""
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
        await self.trigger_data_update(update)

    async def trigger_data_update(self, update: DataUpdate):
        # make sure the id has a unique id for tracking
        if update.id is None:
            update.id = uuid.uuid4().hex
        logger.info("Triggering data update with id: {id}", id=update.id)

        # Fetching should be concurrent, but storing should be done in the original order
        store_queue_number = await self._updates_storing_queue.take_a_number()
        self._tasks.add_task(self._update_policy_data(update, store_queue_number))

    async def get_policy_data_config(self, url: str = None) -> DataSourceConfig:
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
                response = await session.get(url, **self._ssl_context_kwargs)
                if response.status == 200:
                    return DataSourceConfig.parse_obj(await response.json())
                else:
                    error_details = await response.json()
                    raise ClientError(
                        f"Fetch data sources failed with status code {response.status}, error: {error_details}"
                    )
        except:
            logger.exception(f"Failed to load data sources config")
            raise

    async def get_base_policy_data(
        self, config_url: str = None, data_fetch_reason="Initial load"
    ):
        """Load data into the policy store according to the data source's
        config provided in the config URL.

        Args:
            config_url (str, optional): URL to retrieve data sources config from. Defaults to None ( self._data_sources_config_url).
            data_fetch_reason (str, optional): Reason to log for the update operation. Defaults to "Initial load".
        """
        logger.info(
            "Performing data configuration, reason: {reason}", reason=data_fetch_reason
        )
        await self._stop_polling_update_tasks()  # If this is a reconnect - should stop previously received periodic updates
        sources_config = await self.get_policy_data_config(url=config_url)

        init_entries, periodic_entries = [], []
        for entry in sources_config.entries:
            (
                periodic_entries
                if (entry.periodic_update_interval is not None)
                else init_entries
            ).append(entry)

        # Process one time entries now
        update = DataUpdate(reason=data_fetch_reason, entries=init_entries)
        await self.trigger_data_update(update)

        # Schedule repeated processing of periodic polling entries
        async def _trigger_update_with_entry(entry):
            await self.trigger_data_update(
                DataUpdate(reason="Periodic Update", entries=[entry])
            )

        for entry in periodic_entries:
            repeat_process_entry = repeated_call(
                partial(_trigger_update_with_entry, entry),
                entry.periodic_update_interval,
                logger=logger,
            )
            self._polling_update_tasks.append(asyncio.create_task(repeat_process_entry))

    async def on_connect(self, client: PubSubClient, channel: RpcChannel):
        """Pub/Sub on_connect callback On connection to backend, whether its
        the first connection, or reconnecting after downtime, refetch the state
        opa needs.

        As long as the connection is alive we know we are in sync with
        the server, when the connection is lost we assume we need to
        start from scratch.
        """
        logger.info("Connected to server")
        if self._fetch_on_connect:
            await self.get_base_policy_data()
        if opal_common_config.STATISTICS_ENABLED:
            await self._client.wait_until_ready()
            # publish statistics to the server about new connection from client (only if STATISTICS_ENABLED is True, default to False)
            await self._client.publish(
                [opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL],
                data={
                    "topics": self._data_topics,
                    "client_id": self._opal_client_id,
                    "rpc_id": channel.id,
                },
            )

    async def on_disconnect(self, channel: RpcChannel):
        logger.info("Disconnected from server")

    async def start(self):
        logger.info("Launching data updater")
        await self._callbacks_reporter.start()
        await self._updates_storing_queue.start_queue_handling(
            self._store_fetched_update
        )
        if self._subscriber_task is None:
            self._subscriber_task = asyncio.create_task(self._subscriber())
            await self._data_fetcher.start()

    async def _subscriber(self):
        """Coroutine meant to be spunoff with create_task to listen in the
        background for data events and pass them to the data_fetcher."""
        logger.info("Subscribing to topics: {topics}", topics=self._data_topics)
        self._client = PubSubClient(
            self._data_topics,
            self._update_policy_data_callback,
            methods_class=TenantAwareRpcEventClientMethods,
            on_connect=[self.on_connect, *self._on_connect_callbacks],
            on_disconnect=[self.on_disconnect, *self._on_disconnect_callbacks],
            extra_headers=self._extra_headers,
            keep_alive=opal_client_config.KEEP_ALIVE_INTERVAL,
            server_uri=self._server_url,
            **self._ssl_context_kwargs,
        )
        async with self._client:
            await self._client.wait_until_done()

    async def _stop_polling_update_tasks(self):
        if len(self._polling_update_tasks) > 0:
            for task in self._polling_update_tasks:
                task.cancel()
            await asyncio.gather(*self._polling_update_tasks, return_exceptions=True)
            self._polling_update_tasks = []

    async def stop(self):
        self._stopping = True
        logger.info("Stopping data updater")

        # disconnect from Pub/Sub
        if self._client is not None:
            try:
                await asyncio.wait_for(self._client.disconnect(), timeout=3)
            except asyncio.TimeoutError:
                logger.debug(
                    "Timeout waiting for DataUpdater pubsub client to disconnect"
                )

        # stop periodic updates
        await self._stop_polling_update_tasks()

        # stop subscriber task
        if self._subscriber_task is not None:
            logger.debug("Cancelling DataUpdater subscriber task")
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError as exc:
                logger.debug(
                    "DataUpdater subscriber task was force-cancelled: {exc}",
                    exc=repr(exc),
                )
            self._subscriber_task = None
            logger.debug("DataUpdater subscriber task was cancelled")

        # stop the data fetcher
        logger.debug("Stopping data fetcher")
        await self._data_fetcher.stop()

        # stop queue handling
        await self._updates_storing_queue.stop_queue_handling()

        # stop the callbacks reporter
        await self._callbacks_reporter.stop()

    async def wait_until_done(self):
        if self._subscriber_task is not None:
            await self._subscriber_task

    @staticmethod
    def calc_hash(data):
        """Calculate an hash (sah256) on the given data, if data isn't a
        string, it will be converted to JSON.

        String are encoded as 'utf-8' prior to hash calculation.
        Returns:
            the hash of the given data (as a a hexdigit string) or '' on failure to process.
        """
        try:
            if not isinstance(data, str):
                data = json.dumps(data, default=pydantic_encoder)
            return hashlib.sha256(data.encode("utf-8")).hexdigest()
        except:
            logger.exception("Failed to calculate hash for data {data}", data=data)
            return ""

    async def _update_policy_data(
        self,
        update: DataUpdate,
        store_queue_number: TakeANumberQueue.Number,
    ):
        """Fetches policy data (policy configuration) from backend and updates
        it into policy-store (i.e. OPA)"""

        if update is None:
            return

        # types / defaults
        urls: List[Tuple[str, FetcherConfig, Optional[JsonableValue]]] = None
        entries: List[DataSourceEntry] = []
        # if we have an actual specification for the update
        if update is not None:
            # Check each entry's topics to only process entries designated to us
            entries = [
                entry
                for entry in update.entries
                if entry.topics
                and not set(entry.topics).isdisjoint(set(self._data_topics))
            ]
            urls = []
            for entry in entries:
                config = entry.config
                if self._shard_id is not None:
                    headers = config.get("headers", {})
                    headers.update({"X-Shard-ID": self._shard_id})
                    config["headers"] = headers
                urls.append((entry.url, config, entry.data))

        if len(entries) > 0:
            logger.info("Fetching policy data", urls=repr(urls))
        else:
            logger.warning(
                "None of the update's entries are designated to subscribed topics"
            )

        # Urls may be None - handle_urls has a default for None
        policy_data_with_urls = await self._data_fetcher.handle_urls(urls)
        store_queue_number.put((update, entries, policy_data_with_urls))

    async def _store_fetched_update(self, update_item):
        (update, entries, policy_data_with_urls) = update_item

        # track the result of each url in order to report back
        reports: List[DataEntryReport] = []

        # Save the data from the update
        # We wrap our interaction with the policy store with a transaction
        async with self._policy_store.transaction_context(
            update.id, transaction_type=TransactionType.data
        ) as store_transaction:
            # for intellisense treat store_transaction as a PolicyStoreClient (which it proxies)
            store_transaction: BasePolicyStoreClient
            error_content = None
            for (url, fetch_config, result), entry in itertools.zip_longest(
                policy_data_with_urls, entries
            ):
                fetched_data_successfully = True

                if isinstance(result, Exception):
                    fetched_data_successfully = False
                    logger.error(
                        "Failed to fetch url {url}, got exception: {exc}",
                        url=url,
                        exc=result,
                    )

                if isinstance(
                    result, aiohttp.ClientResponse
                ) and is_http_error_response(
                    result
                ):  # error responses
                    fetched_data_successfully = False
                    try:
                        error_content = await result.json()
                        logger.error(
                            "Failed to fetch url {url}, got response code {status} with error: {error}",
                            url=url,
                            status=result.status,
                            error=error_content,
                        )
                    except json.JSONDecodeError:
                        error_content = await result.text()
                        logger.error(
                            "Failed to decode response from url:{url}, got response code {status} with response: {error}",
                            url=url,
                            status=result.status,
                            error=error_content,
                        )
                store_transaction._update_remote_status(
                    url=url,
                    status=fetched_data_successfully,
                    error=str(error_content),
                )

                if fetched_data_successfully:
                    # get path to store the URL data (default mode (None) is as "" - i.e. as all the data at root)
                    policy_store_path = "" if entry is None else entry.dst_path
                    # None is not valid - use "" (protect from missconfig)
                    if policy_store_path is None:
                        policy_store_path = ""
                    # fix opa_path (if not empty must start with "/" to be nested under data)
                    if policy_store_path != "" and not policy_store_path.startswith(
                        "/"
                    ):
                        policy_store_path = f"/{policy_store_path}"
                    policy_data = result
                    # Create a report on the data-fetching
                    report = DataEntryReport(
                        entry=entry, hash=self.calc_hash(policy_data), fetched=True
                    )

                    try:
                        if (
                            opal_client_config.SPLIT_ROOT_DATA
                            and policy_store_path in ("/", "")
                            and isinstance(policy_data, dict)
                        ):
                            await self._set_split_policy_data(
                                store_transaction,
                                url=url,
                                save_method=entry.save_method,
                                data=policy_data,
                            )
                        else:
                            await self._set_policy_data(
                                store_transaction,
                                url=url,
                                path=policy_store_path,
                                save_method=entry.save_method,
                                data=policy_data,
                            )
                        # No exception we we're able to save to the policy-store
                        report.saved = True
                        # save the report for the entry
                        reports.append(report)
                    except Exception:
                        logger.exception("Failed to save data update to policy-store")
                        # we failed to save to policy-store
                        report.saved = False
                        # save the report for the entry
                        reports.append(report)
                        # re-raise so the context manager will be aware of the failure
                        raise
                else:
                    report = DataEntryReport(entry=entry, fetched=False, saved=False)
                    # save the report for the entry
                    reports.append(report)
        # should we send a report to defined callbackers?
        if self._should_send_reports:
            # spin off reporting (no need to wait on it)
            whole_report = DataUpdateReport(update_id=update.id, reports=reports)
            extra_callbacks = self._callbacks_register.normalize_callbacks(
                update.callback.callbacks
            )
            self._tasks.add_task(
                self._callbacks_reporter.report_update_results(
                    whole_report, extra_callbacks
                )
            )

    async def _set_split_policy_data(
        self, tx, url: str, save_method: str, data: Dict[str, Any]
    ):
        """Split data writes to root ("/") path, so they won't overwrite other
        sources."""
        logger.info("Splitting root data to {n} keys", n=len(data))

        for prefix, obj in data.items():
            await self._set_policy_data(
                tx, url=url, path=f"/{prefix}", save_method=save_method, data=obj
            )

    async def _set_policy_data(
        self, tx, url: str, path: str, save_method: str, data: JsonableValue
    ):
        logger.info(
            "Saving fetched data to policy-store: source url='{url}', destination path='{path}'",
            url=url,
            path=path or "/",
        )
        if save_method == "PUT":
            await tx.set_policy_data(data, path=path)
        else:
            await tx.patch_policy_data(data, path=path)

    @property
    def callbacks_reporter(self) -> CallbacksReporter:
        return self._callbacks_reporter
