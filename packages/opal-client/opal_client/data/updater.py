import asyncio
import hashlib
import json
import uuid
from functools import partial
from typing import Any, Dict, List, Optional

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
    PolicyStoreTransactionContextManager,
)
from opal_client.policy_store.policy_store_client_factory import (
    DEFAULT_POLICY_STORE_GETTER,
)
from opal_common.async_utils import TasksPool, repeated_call
from opal_common.config import opal_common_config
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
from opal_common.synchronization.hierarchical_lock import HierarchicalLock
from opal_common.utils import get_authorization_header
from pydantic.json import pydantic_encoder


class DataUpdater:
    """The DataUpdater is responsible for synchronizing data sources with the
    policy store (e.g. OPA). It listens to Pub/Sub topics for data updates,
    fetches the updated data, and writes it into the policy store. The updater
    also supports a "base fetch" flow on startup or reconnection, pulling data
    from a configuration endpoint.

    Key Responsibilities:
      - Subscribe to data update topics.
      - Fetch new or changed data (using Fetchers, e.g. HTTP)
      - Write updates to the policy store, ensuring concurrency safety.
      - Periodically poll data sources (if configured).
      - Report or callback the outcome of data updates (if configured).
    """

    def __init__(
        self,
        token: str = None,
        pubsub_url: str = None,
        data_sources_config_url: str = None,
        fetch_on_connect: bool = True,
        data_topics: List[str] = None,
        policy_store: BasePolicyStoreClient = None,
        should_send_reports: Optional[bool] = None,
        data_fetcher: Optional[DataFetcher] = None,
        callbacks_register: Optional[CallbacksRegister] = None,
        opal_client_id: str = None,
        shard_id: Optional[str] = None,
        on_connect: List[PubSubOnConnectCallback] = None,
        on_disconnect: List[OnDisconnectCallback] = None,
    ):
        """Initializes the DataUpdater with the necessary configuration and
        clients.

        Args:
            token (str, optional): Auth token to include in connections to OPAL server. Defaults to CLIENT_TOKEN.
            pubsub_url (str, optional): URL for Pub/Sub updates for data. Defaults to OPAL_SERVER_PUBSUB_URL.
            data_sources_config_url (str, optional): URL to retrieve base data configuration. Defaults to DEFAULT_DATA_SOURCES_CONFIG_URL.
            fetch_on_connect (bool, optional): Whether to fetch all data immediately upon connection.
            data_topics (List[str], optional): Pub/Sub topics to subscribe to. Defaults to DATA_TOPICS.
            policy_store (BasePolicyStoreClient, optional): The client used to store data. Defaults to DEFAULT_POLICY_STORE.
            should_send_reports (bool, optional): Whether to report on data updates to callbacks. Defaults to SHOULD_REPORT_ON_DATA_UPDATES.
            data_fetcher (DataFetcher, optional): Custom data fetching engine.
            callbacks_register (CallbacksRegister, optional): Manages user-defined callbacks.
            opal_client_id (str, optional): A unique identifier for this OPAL client.
            shard_id (str, optional): A partition/shard identifier. Translates to an HTTP header.
            on_connect (List[PubSubOnConnectCallback], optional): Extra on-connect callbacks.
            on_disconnect (List[OnDisconnectCallback], optional): Extra on-disconnect callbacks.
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
            # Namespacing the data topics for the specific scope
            self._data_topics = [
                f"{self._scope_id}:data:{topic}" for topic in self._data_topics
            ]

        # Should the client fetch data when it first connects (or reconnects)
        self._fetch_on_connect = fetch_on_connect
        # Policy store client
        self._policy_store = policy_store or DEFAULT_POLICY_STORE_GETTER()

        self._should_send_reports = (
            should_send_reports
            if should_send_reports is not None
            else opal_client_config.SHOULD_REPORT_ON_DATA_UPDATES
        )

        # Will be set once we subscribe and connect
        self._client: Optional[PubSubClient] = None
        self._subscriber_task: Optional[asyncio.Task] = None

        # DataFetcher is a helper that can handle different data sources (HTTP, local, etc.)
        self._data_fetcher = data_fetcher or DataFetcher()
        self._callbacks_register = callbacks_register or CallbacksRegister()
        self._callbacks_reporter = CallbacksReporter(self._callbacks_register)

        self._token = token
        self._shard_id = shard_id
        self._server_url = pubsub_url
        self._data_sources_config_url = data_sources_config_url
        self._opal_client_id = opal_client_id

        # Prepare any extra headers (token, shard id, etc.)
        self._extra_headers = []
        if self._token is not None:
            self._extra_headers.append(get_authorization_header(self._token))
        if self._shard_id is not None:
            self._extra_headers.append(("X-Shard-ID", self._shard_id))
        if len(self._extra_headers) == 0:
            self._extra_headers = None

        self._stopping = False
        self._custom_ssl_context = get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context} if self._custom_ssl_context else {}
        )

        # TaskGroup to manage data updates and callbacks background tasks (with graceful shutdown)
        self._tasks = TasksPool()

        # Lock to prevent multiple concurrent writes to the same path
        self._dst_lock = HierarchicalLock()

        # References to repeated polling tasks (periodic data fetch)
        self._polling_update_tasks = []

        # Optional user-defined hooks for connection lifecycle
        self._on_connect_callbacks = on_connect or []
        self._on_disconnect_callbacks = on_disconnect or []

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if not self._stopping:
            await self.stop()

    async def _update_policy_data_callback(self, data: Optional[dict] = None, topic=""):
        """Callback invoked by the Pub/Sub client whenever a data update is
        published on one of our subscribed topics.

        Calls trigger_data_update() with the DataUpdate object extracted
        from 'data'.
        """
        if data is not None:
            reason = data.get("reason", "")
        else:
            reason = "Periodic update"

        logger.info("Updating policy data, reason: {reason}", reason=reason)
        update = DataUpdate.parse_obj(data)
        await self.trigger_data_update(update)

    async def trigger_data_update(self, update: DataUpdate):
        """Queues up a data update to run in the background. If no update ID is
        provided, generate one for tracking/logging.

        Note:
            We spin off the data update in the background so that multiple updates
            can run concurrently. Internally, the `_update_policy_data` method uses
            a hierarchical lock to avoid race conditions when multiple updates try
            to write to the same destination path.
        """
        # Ensure we have a unique update ID
        if update.id is None:
            update.id = uuid.uuid4().hex

        logger.info("Triggering data update with id: {id}", id=update.id)

        # Run the update in the background concurrently with other updates
        # The TaskGroup will manage the lifecycle of this task,
        # managing graceful shutdown of the updater without losing running data updates
        self._tasks.add_task(self._update_policy_data(update))

    async def get_policy_data_config(self, url: str = None) -> DataSourceConfig:
        """Fetches the DataSourceConfig (list of DataSourceEntry) from the
        provided URL.

        Args:
            url (str, optional): The URL to fetch data sources config from. Defaults to
                                 self._data_sources_config_url if None is given.

        Raises:
            ClientError: If the server responds with an error status.

        Returns:
            DataSourceConfig: The parsed config containing data entries.
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
            logger.exception("Failed to load data sources config")
            raise

    async def get_base_policy_data(
        self, config_url: str = None, data_fetch_reason="Initial load"
    ):
        """Fetches an initial (or base) set of data from the configuration URL
        and stores it in the policy store.

        This method also sets up any periodic data polling tasks for entries
        that specify a 'periodic_update_interval'.

        Args:
            config_url (str, optional): A specific config URL to fetch from. If not given,
                                        uses self._data_sources_config_url.
            data_fetch_reason (str, optional): Reason for logging this fetch. Defaults to
                                               "Initial load".
        """
        logger.info(
            "Performing data configuration, reason: {reason}", reason=data_fetch_reason
        )

        # If we're reconnecting, stop any old periodic tasks before fetching anew
        await self._stop_polling_update_tasks()

        # Fetch the base config with all data entries
        sources_config = await self.get_policy_data_config(url=config_url)

        init_entries, periodic_entries = [], []
        for entry in sources_config.entries:
            if entry.periodic_update_interval is not None:
                periodic_entries.append(entry)
            else:
                init_entries.append(entry)

        # Process one-time entries now
        update = DataUpdate(reason=data_fetch_reason, entries=init_entries)
        await self.trigger_data_update(update)

        # Schedule repeated processing (polling) of periodic entries
        async def _trigger_update_with_entry(entry: DataSourceEntry):
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
        """Invoked when the Pub/Sub client establishes a connection to the
        server.

        By default, this re-fetches base policy data. Also publishes a
        statistic event if statistics are enabled.
        """
        logger.info("Connected to server")
        if self._fetch_on_connect:
            await self.get_base_policy_data()
        if opal_common_config.STATISTICS_ENABLED:
            # Publish stats about the newly connected client
            await self._client.wait_until_ready()
            await self._client.publish(
                [opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL],
                data={
                    "topics": self._data_topics,
                    "client_id": self._opal_client_id,
                    "rpc_id": channel.id,
                },
            )

    async def on_disconnect(self, channel: RpcChannel):
        """Invoked when the Pub/Sub client disconnects from the server."""
        logger.info("Disconnected from server")

    async def start(self):
        """
        Starts the DataUpdater:
          - Begins listening for Pub/Sub data update events.
          - Starts the callbacks reporter for asynchronous callback tasks.
          - Starts the DataFetcher if not already running.
        """
        logger.info("Launching data updater")
        await self._callbacks_reporter.start()

        if self._subscriber_task is None:
            # The subscriber task runs in the background, receiving data update events
            self._subscriber_task = asyncio.create_task(self._subscriber())
            await self._data_fetcher.start()

    async def _subscriber(self):
        """The main loop for subscribing to Pub/Sub topics.

        Waits for data update notifications and dispatches them to our
        callback.
        """
        logger.info("Subscribing to topics: {topics}", topics=self._data_topics)
        self._client = PubSubClient(
            self._data_topics,
            self._update_policy_data_callback,
            methods_class=TenantAwareRpcEventClientMethods,
            on_connect=[self.on_connect, *self._on_connect_callbacks],
            on_disconnect=[self.on_disconnect, *self._on_disconnect_callbacks],
            additional_headers=self._extra_headers,
            keep_alive=opal_client_config.KEEP_ALIVE_INTERVAL,
            server_uri=self._server_url,
            **self._ssl_context_kwargs,
        )
        async with self._client:
            await self._client.wait_until_done()

    async def _stop_polling_update_tasks(self):
        """Cancels all periodic polling tasks (if any).

        Used on reconnection or shutdown to ensure we don't have stale
        tasks still running.
        """
        if self._polling_update_tasks:
            for task in self._polling_update_tasks:
                task.cancel()
            await asyncio.gather(*self._polling_update_tasks, return_exceptions=True)
            self._polling_update_tasks = []

    async def stop(self):
        """
        Cleanly shuts down the DataUpdater:
          - Disconnects the Pub/Sub client.
          - Stops polling tasks.
          - Cancels the subscriber background task.
          - Stops the data fetcher and callback reporter.
        """
        self._stopping = True
        logger.info("Stopping data updater")

        if self._client is not None:
            try:
                await asyncio.wait_for(self._client.disconnect(), timeout=3)
            except asyncio.TimeoutError:
                logger.debug(
                    "Timeout waiting for DataUpdater pubsub client to disconnect"
                )

        await self._stop_polling_update_tasks()

        # Cancel the subscriber task
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

        # Stop the DataFetcher
        logger.debug("Stopping data fetcher")
        await self._data_fetcher.stop()

        # Stop the callbacks reporter
        await self._callbacks_reporter.stop()

        # Exit the TaskGroup context
        await self._tasks.shutdown()

    async def wait_until_done(self):
        """Blocks until the Pub/Sub subscriber task completes.

        Typically, this runs indefinitely unless a stop/shutdown event
        occurs.
        """
        if self._subscriber_task is not None:
            await self._subscriber_task

    @staticmethod
    def calc_hash(data: JsonableValue) -> str:
        """Calculates a SHA-256 hash of the given data to be used to identify
        the updates (e.g. in logging reports on the transactions)  . If 'data'
        is not a string, it is first serialized to JSON. Returns an empty
        string on failure.

        Args:
            data (JsonableValue): The data to be hashed.

        Returns:
            str: The hexadecimal representation of the SHA-256 hash.
        """
        try:
            if not isinstance(data, str):
                data = json.dumps(data, default=pydantic_encoder)
            return hashlib.sha256(data.encode("utf-8")).hexdigest()
        except Exception as e:
            logger.exception(f"Failed to calculate hash for data {data}: {e}")
            return ""

    async def _update_policy_data(self, update: DataUpdate) -> None:
        """Performs the core data update process for the given DataUpdate
        object.

        Steps:
          1. Iterate over the DataUpdate entries.
          2. For each entry, check if any of its topics match our client's topics.
          3. Acquire a lock for the destination path, so we don't fetch and overwrite concurrently.
             - Note: This means that fetches that can technically happen concurrently wait on one another.
                          This can be improved with  a Fetcher-Writer Lock ( a la Reader-Writer Lock ) pattern
          4. Fetch the data from the source (if applicable).
          5. Write the data into the policy store.
          6. Collect a report (success/failure, hash of the data, etc.).
          7. Send a consolidated report after processing all entries.

        Args:
            update (DataUpdate): The data update instructions (entries, reason, etc.).

        Returns:
            None
        """
        reports: list[DataEntryReport] = []

        for entry in update.entries:
            if not entry.topics:
                logger.debug("Data entry {entry} has no topics, skipping", entry=entry)
                continue

            # Only process entries that match one of our subscribed data topics
            if set(entry.topics).isdisjoint(set(self._data_topics)):
                logger.debug(
                    "Data entry {entry} has no topics matching the data topics, skipping",
                    entry=entry,
                )
                continue

            transaction_context = self._policy_store.transaction_context(
                update.id, transaction_type=TransactionType.data
            )

            # Acquire a per-destination lock to avoid overwriting the same path concurrently
            async with (
                transaction_context as store_transaction,
                self._dst_lock.lock(entry.dst_path),
            ):
                report = await self._fetch_and_save_data(entry, store_transaction)

            reports.append(report)

        await self._send_reports(reports, update)

    async def _send_reports(self, reports: list[DataEntryReport], update: DataUpdate):
        """Handles the reporting of completed data updates back to callbacks.

        Args:
            reports (List[DataEntryReport]): List of individual entry reports.
            update (DataUpdate): The overall DataUpdate object (contains reason, etc.).
        """
        if self._should_send_reports:
            # Merge into a single DataUpdateReport
            whole_report = DataUpdateReport(update_id=update.id, reports=reports)
            extra_callbacks = self._callbacks_register.normalize_callbacks(
                update.callback.callbacks
            )
            # Asynchronously send the report to any configured callbacks
            self._tasks.add_task(
                self._callbacks_reporter.report_update_results(
                    whole_report, extra_callbacks
                )
            )

    async def _fetch_and_save_data(
        self,
        entry: DataSourceEntry,
        store_transaction: PolicyStoreTransactionContextManager,
    ) -> DataEntryReport:
        """Orchestrates fetching data from a source and saving it into the
        policy store.

        Flow:
          1. Attempt to fetch data via the data fetcher (e.g., HTTP).
          2. If data is fetched successfully, store it in the policy store.
          3. Return a DataEntryReport indicating success/failure of each step.

        Args:
            entry (DataSourceEntry): The configuration details of the data source entry.
            store_transaction (PolicyStoreTransactionContextManager): An active
                transaction to the policy store.

        Returns:
            DataEntryReport: Includes information about whether data was fetched,
                saved, and the computed hash for the data if successfully saved.
        """
        try:
            result = await self._fetch_data(entry)
        except Exception as e:
            store_transaction._update_remote_status(
                url=entry.url, status=False, error=str(e)
            )
            return DataEntryReport(entry=entry, fetched=False, saved=False)

        try:
            await self._store_fetched_data(entry, result, store_transaction)
        except Exception as e:
            logger.exception("Failed to save data update to policy-store: {exc}", exc=e)
            store_transaction._update_remote_status(
                url=entry.url,
                status=False,
                error=f"Failed to save data to policy store: {e}",
            )
            return DataEntryReport(
                entry=entry, hash=self.calc_hash(result), fetched=True, saved=False
            )
        else:
            store_transaction._update_remote_status(
                url=entry.url, status=True, error=""
            )
            return DataEntryReport(
                entry=entry, hash=self.calc_hash(result), fetched=True, saved=True
            )

    async def _fetch_data(self, entry: DataSourceEntry) -> JsonableValue:
        """Fetches data from a data source using the configured data fetcher.
        Handles fetch errors, HTTP errors, and empty responses.

        Args:
            entry (DataSourceEntry): The configuration specifying how and where to fetch data.

        Returns:
            JsonableValue: The fetched data, as a JSON-serializable object.
        """
        try:
            result = await self._data_fetcher.handle_url(
                url=entry.url,
                config=entry.config,
                data=entry.data,
            )
        except Exception as e:
            logger.exception(
                "Failed to fetch data for entry {entry} with exception {exc}",
                entry=entry,
                exc=e,
            )
            raise Exception(f"Failed to fetch data for entry {entry.url}: {e}")

        if result is None:
            raise Exception(f"Fetched data is empty for entry {entry.url}")

        if isinstance(result, aiohttp.ClientResponse) and is_http_error_response(
            result
        ):
            error_content = await result.text()
            logger.error(
                "Failed to decode response from url: '{url}', got response code {status} with response: {error}",
                url=entry.url,
                status=result.status,
                error=error_content,
            )
            raise Exception(
                f"Failed to decode response from url: '{entry.url}', got response code {result.status} with response: {error_content}"
            )

        return result

    async def _store_fetched_data(
        self,
        entry: DataSourceEntry,
        result: JsonableValue,
        store_transaction: PolicyStoreTransactionContextManager,
    ) -> None:
        """Decides how to store fetched data (entirely or split by root keys)
        in the policy store based on the configuration.

        Args:
            entry (DataSourceEntry): The configuration specifying how and where to store data.
            result (JsonableValue): The fetched data to be stored.
            store_transaction (PolicyStoreTransactionContextManager): The policy store
                transaction under which to perform the write operations.

        Raises:
            Exception: If storing data fails for any reason.
        """
        policy_store_path = entry.dst_path or ""
        if policy_store_path and not policy_store_path.startswith("/"):
            policy_store_path = f"/{policy_store_path}"

        # If splitting root-level data is enabled and the path is "/", each top-level key
        # is stored individually to avoid overwriting the entire data root.
        if (
            opal_client_config.SPLIT_ROOT_DATA
            and policy_store_path in ("/", "")
            and isinstance(result, dict)
        ):
            await self._set_split_policy_data(
                store_transaction,
                url=entry.url,
                save_method=entry.save_method,
                data=result,
            )
        else:
            await self._set_policy_data(
                store_transaction,
                url=entry.url,
                path=policy_store_path,
                save_method=entry.save_method,
                data=result,
            )

    async def _set_split_policy_data(
        self,
        tx: PolicyStoreTransactionContextManager,
        url: str,
        save_method: str,
        data: Dict[str, Any],
    ):
        """Splits data writes for root path ("/") so we don't overwrite
        existing keys.

        For each top-level key in the dictionary, we create a sub-path under "/<key>"
        and save the corresponding value.

        Args:
            tx (PolicyStoreTransactionContextManager): The active store transaction.
            url (str): The data source URL (used for logging/reporting).
            save_method (str): Either "PUT" (full overwrite) or "PATCH" (merge).
            data (Dict[str, Any]): The dictionary to be split and stored.
        """
        logger.info("Splitting root data to {n} keys", n=len(data))

        for prefix, obj in data.items():
            await self._set_policy_data(
                tx,
                url=url,
                path=f"/{prefix}",
                save_method=save_method,
                data=obj,
            )

    async def _set_policy_data(
        self,
        tx: PolicyStoreTransactionContextManager,
        url: str,
        path: str,
        save_method: str,
        data: JsonableValue,
    ):
        """Persists data to a specific path in the policy store.

        Args:
            tx (PolicyStoreTransactionContextManager): The active store transaction.
            url (str): The URL of the source data (used for logging/reporting).
            path (str): The policy store path where data will be stored (e.g. "/roles").
            save_method (str): Either "PUT" (full overwrite) or "PATCH" (partial merge).
            data (JsonableValue): The data to be written.
        """
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
        """Provides external access to the CallbacksReporter instance, so that
        users of DataUpdater can register custom callbacks or manipulate
        reporting flows.

        Returns:
            CallbacksReporter: The internal callbacks reporter.
        """
        return self._callbacks_reporter
