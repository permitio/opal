"""Simple HTTP get data fetcher using requests supports."""

from enum import Enum
from typing import Any, Union, cast

import httpx
from aiohttp import ClientResponse, ClientSession
from opal_common.config import opal_common_config
from opal_common.fetcher.events import FetcherConfig, FetchEvent
from opal_common.fetcher.fetch_provider import BaseFetchProvider
from opal_common.fetcher.logger import get_logger
from opal_common.http_utils import is_http_error_response
from opal_common.security.sslcontext import get_custom_ssl_context
from pydantic import validator

logger = get_logger("http_fetch_provider")


class HttpMethods(Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    PATCH = "patch"
    HEAD = "head"
    DELETE = "delete"


class HttpFetcherConfig(FetcherConfig):
    """Config for HttpFetchProvider's Adding HTTP headers."""

    headers: dict = None
    is_json: bool = True
    process_data: bool = True
    method: HttpMethods = HttpMethods.GET
    data: Any = None

    @validator("method")
    def force_enum(cls, v):
        if isinstance(v, str):
            return HttpMethods(v)
        if isinstance(v, HttpMethods):
            return v
        raise ValueError(f"invalid value: {v}")

    class Config:
        use_enum_values = True


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
        self._custom_ssl_context = get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context}
            if self._custom_ssl_context is not None
            else {}
        )

    def parse_event(self, event: FetchEvent) -> HttpFetchEvent:
        return HttpFetchEvent(**event.dict(exclude={"config"}), config=event.config)

    async def __aenter__(self):
        headers = {}
        if self._event.config.headers is not None:
            headers = self._event.config.headers
        if opal_common_config.HTTP_FETCHER_PROVIDER_CLIENT == "httpx":
            self._session = httpx.AsyncClient(headers=headers)
        else:
            self._session = ClientSession(headers=headers, raise_for_status=True)
        self._session = await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type=None, exc_val=None, tb=None):
        await self._session.__aexit__(exc_type, exc_val, tb)

    async def _fetch_(self):
        logger.debug(f"{self.__class__.__name__} fetching from {self._url}")
        http_method = self.match_http_method_from_type(
            self._session, self._event.config.method
        )
        if self._event.config.data is not None:
            result: Union[ClientResponse, httpx.Response] = await http_method(
                self._url, data=self._event.config.data, **self._ssl_context_kwargs
            )
        else:
            result = await http_method(self._url, **self._ssl_context_kwargs)
        result.raise_for_status()
        return result

    @staticmethod
    def match_http_method_from_type(
        session: Union[ClientSession, httpx.AsyncClient], method_type: HttpMethods
    ):
        return getattr(session, method_type.value)

    @staticmethod
    async def _response_to_data(
        res: Union[ClientResponse, httpx.Response], *, is_json: bool
    ) -> Any:
        if isinstance(res, httpx.Response):
            return res.json() if is_json else res.text
        else:
            res = cast(ClientResponse, res)
            return await (res.json() if is_json else res.text())

    async def _process_(self, res: Union[ClientResponse, httpx.Response]):
        # do not process data when the http response is an error
        if is_http_error_response(res):
            return res

        # if we are asked to process the data before we return it
        if self._event.config.process_data:
            data = await self._response_to_data(res, is_json=self._event.config.is_json)
            return data
        # return raw result
        else:
            return res
