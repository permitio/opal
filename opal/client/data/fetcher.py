import asyncio
from typing import Dict, Any

from opal.config.client.config import DEFAULT_DATA_URL, CLIENT_TOKEN
from opal.common.utils import get_authorization_header
from opal.client.utils import tuple_to_dict
from opal.common.fetcher import FetchingEngine
from opal.common.fetcher.events import FetcherConfig
from opal.common.fetcher.providers.http_get_fetch_provider import HttpGetFetcherConfig

class DataFetcher:
    """
    fetches policy data from backend
    """
    def __init__(self, default_data_url:str=DEFAULT_DATA_URL, token:str=CLIENT_TOKEN):
        """[summary]

        Args:
            default_data_url (str, optional): The URL used to fetch data if no specific url is given in a fetch request. Defaults to DEFAULT_DATA_URL.
            token (str, optional): default auth token. Defaults to CLIENT_TOKEN.
        """
        # The underlying fetching engine
        self._engine = FetchingEngine()
        self._data_url = default_data_url
        self._token = token
        self._auth_headers = tuple_to_dict(get_authorization_header(token))
        self._default_fetcher_config = HttpGetFetcherConfig(headers=self._auth_headers, is_json=True)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """
        Context handler to terminate internal tasks
        """
        await self.stop()

    async def start(self):
        self._engine.start_workers()

    async def stop(self):
        """
        Release internal tasks and resources
        """
        await self._engine.terminate_workers()

    async def _handle_url(self, url, config):
        """
        Helper function wrapping self._engine.handle_url, returning the fetched result with the url used for it
        """
        # ask the engine to get our data
        response = await self._engine.handle_url(url, config=config)
        # store as part of all results
        return url, response

    async def fetch_policy_data(self, urls:Dict[str, FetcherConfig]=None) -> Dict[str, Any]:
        """
        Fetch data for each given url with the (optional) fetching configuration; return the resulting data mapped to each URL

        Args:
            urls (Dict[str, FetcherConfig], optional): Urls (and fetching configuration) to fetch from.
            Defaults to None - init data_url with HttpGetFetcherConfig (loaded with the provided auth token).

        Returns:
            Dict[str, Any]: urls mapped to their resulting fetched data
        """
        # return value - /fetch-results mapped by url
        results_by_url = {}
        # tasks
        tasks = []
        # if no url provided - default to the builtin route
        if urls is None:
            urls = {self._data_url:  self._default_fetcher_config}
        # create a task for each url
        for url, config in urls.items():
            tasks.append(self._handle_url(url, config))
        # wait for all data fetches to complete
        results = await asyncio.gather(*tasks)
        # Map results by urls
        results_by_url = {url: response for url, response in results  }
        # return results
        return results_by_url


