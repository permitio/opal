"""
Simple HTTP get data fetcher using requests
supports 
"""

from aiohttp_requests import requests

from ..fetch_provider import BaseFetchProvider
from ..events import FetcherConfig, FetchEvent
from ..logger import get_logger

logger = get_logger("http_get_fetch_provider")

class HttpGetFetcherConfig(FetcherConfig):
    """
    Config for HttpGetFetchProvider's Adding HTTP headers 
    """
    headers: dict


class HttpGetFetchEvent(FetchEvent):
    fetcher: str = "HttpGetFetchProvider"
    config: HttpGetFetcherConfig = None

class HttpGetFetchProvider(BaseFetchProvider):

    def __init__(self, event: HttpGetFetchEvent) -> None:
        self._event: HttpGetFetchEvent
        super().__init__(event)

    async def _fetch_(self):
        logger.info(f"{self.__class__.__name__} fetching from {self._url}")
        headers = {}
        if self._event.config is not None:
            headers = self._event.config.headers
        result = await requests.get(self._url, headers=headers)
        return result
