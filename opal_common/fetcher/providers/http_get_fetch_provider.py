"""
Simple HTTP get data fetcher using requests
supports 
"""

from aiohttp import ClientResponse, ClientSession
from ..fetch_provider import BaseFetchProvider
from ..events import FetcherConfig, FetchEvent
from ..logger import get_logger

logger = get_logger("http_get_fetch_provider")

class HttpGetFetcherConfig(FetcherConfig):
    """
    Config for HttpGetFetchProvider's Adding HTTP headers 
    """
    headers: dict = None
    is_json: bool = True
    process_data: bool = True

class HttpGetFetchEvent(FetchEvent):
    fetcher: str = "HttpGetFetchProvider"
    config: HttpGetFetcherConfig = None

class HttpGetFetchProvider(BaseFetchProvider):

    def __init__(self, event: HttpGetFetchEvent) -> None:
        self._event: HttpGetFetchEvent
        if event.config is None:
            event.config = HttpGetFetcherConfig()
        super().__init__(event)
        self._session = None

    def parse_event(self, event: FetchEvent) -> HttpGetFetchEvent:
        return HttpGetFetchEvent(**event.dict(exclude={"config"}), config=event.config)   

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
        
        result = await self._session.get(self._url)
        return result

    async def _process_(self, res: ClientResponse):
        # if we are asked to process the data before return it
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
