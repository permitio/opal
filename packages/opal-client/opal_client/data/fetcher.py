import asyncio
from typing import Any, Dict, List, Optional, Tuple

from opal_client.config import opal_client_config
from opal_client.policy_store.base_policy_store_client import JsonableValue
from opal_common.config import opal_common_config
from opal_common.fetcher import FetchingEngine
from opal_common.fetcher.events import FetcherConfig
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.logger import logger
from opal_common.utils import get_authorization_header, tuple_to_dict


class DataFetcher:
    """fetches policy data from backend."""

    def __init__(self, default_data_url: str = None, token: str = None):
        """

        Args:
            default_data_url (str, optional): The URL used to fetch data if no specific url is given in a fetch request. Defaults to DEFAULT_DATA_URL.
            token (str, optional): default auth token. Defaults to CLIENT_TOKEN.
        """
        # defaults
        default_data_url: str = default_data_url or opal_client_config.DEFAULT_DATA_URL
        token: str = token or opal_client_config.CLIENT_TOKEN
        # The underlying fetching engine
        self._engine = FetchingEngine(
            worker_count=opal_common_config.FETCHING_WORKER_COUNT,
            callback_timeout=opal_common_config.FETCHING_CALLBACK_TIMEOUT,
            enqueue_timeout=opal_common_config.FETCHING_ENQUEUE_TIMEOUT,
        )
        self._data_url = default_data_url
        self._token = token
        self._auth_headers = tuple_to_dict(get_authorization_header(token))
        self._default_fetcher_config = HttpFetcherConfig(
            headers=self._auth_headers, is_json=True
        )

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Context handler to terminate internal tasks."""
        await self.stop()

    async def start(self):
        self._engine.start_workers()

    async def stop(self):
        """Release internal tasks and resources."""
        await self._engine.terminate_workers()

    async def handle_url(
        self, url: str, config: FetcherConfig, data: Optional[JsonableValue]
    ):
        """Helper function wrapping self._engine.handle_url."""
        if data is not None:
            logger.info("Data provided inline for url: {url}", url=url)
            return data

        if url is None:
            logger.error("Invalid data update: no embedded data or URL")
            return None

        logger.info("Fetching data from url: {url}", url=url)
        try:
            # ask the engine to get our data
            response = await self._engine.handle_url(url, config=config)
            return response
        except asyncio.TimeoutError as e:
            logger.exception("Timeout while fetching url: {url}", url=url)
            raise

    async def handle_urls(
        self, urls: List[Tuple[str, FetcherConfig, Optional[JsonableValue]]] = None
    ) -> List[Tuple[str, FetcherConfig, Any]]:
        """Fetch data for each given url with the (optional) fetching
        configuration; return the resulting data mapped to each URL.

        Args:
            urls (List[Tuple[str, FetcherConfig]], optional): Urls (and fetching configuration) to fetch from.
            Defaults to None - init data_url with HttpFetcherConfig (loaded with the provided auth token).

        Returns:
            List[Tuple[str,FetcherConfig, Any]]: urls mapped to their resulting fetched data
        """

        # tasks
        tasks = []
        # if no url provided - default to the builtin route
        if urls is None:
            urls = [(self._data_url, self._default_fetcher_config, None)]
        # create a task for each url
        for url, config, data in urls:
            tasks.append(self.handle_url(url, config, data))
        # wait for all data fetches to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results with their matching urls and config
        results_with_url_and_config = [
            (url, config, result)
            for (url, config, data), result in zip(urls, results)
            if result is not None
        ]

        # return results
        return results_with_url_and_config
