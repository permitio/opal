"""
Simple HTTP get data fetcher using requests
supports 
"""

from enum import Enum
from typing import Any
from aiohttp import ClientResponse, ClientSession
from ..fetch_provider import BaseFetchProvider
from ..events import FetcherConfig, FetchEvent
from ..logger import get_logger

logger = get_logger("http_fetch_provider")


class HttpMethods(Enum):
    GET="get"
    POST="post"
    PUT="put"
    PATCH="patch"
    HEAD="head"
    DELETE="delete"
    
class HttpFetcherConfig(FetcherConfig):
    """
    Config for HttpFetchProvider's Adding HTTP headers 
    """
    headers: dict = None
    is_json: bool = True
    process_data: bool = True
    method:HttpMethods = HttpMethods.GET
    data:Any = None


class HttpFetchEvent(FetchEvent):
    fetcher: str = "HttpFetchProvider"
    config: HttpFetcherConfig = None

class HttpFetchProvider(BaseFetchProvider):

    def __init__(self, event: HttpFetchEvent) -> None:
        self._event: HttpFetchEvent
        if event.config is None:
            event.config = HttpFetcherConfig()
        super().__init__(event)
        self._session = None

    def parse_event(self, event: FetchEvent) -> HttpFetchEvent:
        return HttpFetchEvent(**event.dict(exclude={"config"}), config=event.config)   

    async def __aenter__(self):
        headers = {}
        if self._event.config.headers is not None:
            headers = self._event.config.headers        
        self._session = await ClientSession(headers=headers).__aenter__()
        return self 

    async def __aexit__(self, exc_type=None, exc_val=None, tb=None):
        await self._session.__aexit__(exc_type=exc_type, exc_val=exc_val, exc_tb=tb)

    async def _fetch_(self):
        logger.debug(f"{self.__class__.__name__} fetching from {self._url}")
        http_method = self.match_http_method_from_type(self._session, self._event.config.method)
        if self._event.config.data is not None:
            result = await http_method(self._url, data=self._event.config.data)
        else:
            result = await http_method(self._url)
        return result

    @staticmethod
    def match_http_method_from_type(session:ClientSession, method_type:HttpMethods):
        return getattr(session, method_type.value)

    async def _process_(self, res: ClientResponse):
        # if we are asked to process the data before we return it
        if self._event.config.process_data:
            # if data is JSON
            if self._event.config.is_json:
                data = await res.json()
            else:
                data = await res.text() 
            return data
        # return raw result
        else:
            return res
