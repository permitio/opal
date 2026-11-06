"""Simple HTTP get data fetcher using requests supports."""

from enum import Enum
from typing import Any, ClassVar, Dict, Optional, Set, Union, cast

import httpx
from aiohttp import ClientResponse, ClientSession, ClientTimeout
from opal_common.config import opal_common_config
from opal_common.fetcher.events import FetcherConfig, FetchEvent
from opal_common.fetcher.fetch_provider import BaseFetchProvider
from opal_common.fetcher.logger import get_logger
from opal_common.http_utils import is_http_error_response, redact_url
from opal_common.security.sslcontext import get_custom_ssl_context
from pydantic import ConfigDict, field_validator

logger = get_logger("http_fetch_provider")


class FetchNotModified:
    """Sentinel returned by HttpFetchProvider when a conditional HTTP request
    receives a 304 Not Modified response."""

    def __repr__(self) -> str:
        return "FETCH_NOT_MODIFIED"


FETCH_NOT_MODIFIED = FetchNotModified()

# In-memory HTTP validator cache (ETag / Last-Modified) keyed by data source entry.
_CONDITIONAL_VALIDATORS: Dict[str, Dict[str, str]] = {}


def clear_conditional_validators() -> None:
    """Clear cached HTTP validators (e.g. on base fetch / reconnect / store
    reset)."""
    _CONDITIONAL_VALIDATORS.clear()


class HttpMethods(Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    PATCH = "patch"
    HEAD = "head"
    DELETE = "delete"


class HttpFetcherConfig(FetcherConfig):
    """Config for HttpFetchProvider's Adding HTTP headers."""

    # ``headers`` carries Authorization tokens and ``data`` the (possibly
    # sensitive) payload - mask both in repr/str so they never leak into logs.
    _redacted_repr_fields: ClassVar[Set[str]] = {"headers", "data"}

    model_config = ConfigDict(use_enum_values=True)

    headers: Optional[dict] = None
    is_json: bool = True
    process_data: bool = True
    method: HttpMethods = HttpMethods.GET
    data: Any = None
    conditional_request: bool = False
    cache_key: Optional[str] = None

    @field_validator("method")
    @classmethod
    def force_enum(cls, v):
        if isinstance(v, str):
            return HttpMethods(v)
        if isinstance(v, HttpMethods):
            return v
        raise ValueError(f"invalid value: {v}")


class HttpFetchEvent(FetchEvent):
    fetcher: str = "HttpFetchProvider"
    config: Optional[HttpFetcherConfig] = None


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
        return HttpFetchEvent(
            **event.model_dump(exclude={"config"}), config=event.config
        )

    def _validator_key(self) -> str:
        if self._event.config.cache_key:
            return self._event.config.cache_key
        method = (
            self._event.config.method.value
            if isinstance(self._event.config.method, HttpMethods)
            else str(self._event.config.method)
        )
        return f"{method}:{self._url}:json={self._event.config.is_json}"

    async def __aenter__(self):
        headers = (
            dict(self._event.config.headers)
            if self._event.config.headers is not None
            else {}
        )
        if self._event.config.conditional_request:
            validator = _CONDITIONAL_VALIDATORS.get(self._validator_key())
            if validator:
                lower_keys = {k.lower() for k in headers}
                if "etag" in validator and "if-none-match" not in lower_keys:
                    headers["If-None-Match"] = validator["etag"]
                if (
                    "last_modified" in validator
                    and "if-modified-since" not in lower_keys
                ):
                    headers["If-Modified-Since"] = validator["last_modified"]
        timeout = opal_common_config.HTTP_FETCHER_TIMEOUT
        if opal_common_config.HTTP_FETCHER_PROVIDER_CLIENT == "httpx":
            self._session = httpx.AsyncClient(
                headers=headers, timeout=timeout, trust_env=True
            )
        else:
            self._session = ClientSession(
                headers=headers,
                raise_for_status=True,
                timeout=ClientTimeout(total=timeout),
                trust_env=True,
            )
        self._session = await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type=None, exc_val=None, tb=None):
        await self._session.__aexit__(exc_type, exc_val, tb)

    async def _fetch_(self):
        logger.debug(f"{self.__class__.__name__} fetching from {redact_url(self._url)}")
        http_method = self.match_http_method_from_type(
            self._session, self._event.config.method
        )
        if self._event.config.data is not None:
            result: Union[ClientResponse, httpx.Response] = await http_method(
                self._url, data=self._event.config.data, **self._ssl_context_kwargs
            )
        else:
            result = await http_method(self._url, **self._ssl_context_kwargs)
        status_code = getattr(result, "status", None) or getattr(
            result, "status_code", None
        )
        if not (self._event.config.conditional_request and status_code == 304):
            result.raise_for_status()
        if (
            self._event.config.conditional_request
            and status_code is not None
            and 200 <= status_code < 300
        ):
            res_headers = getattr(result, "headers", None) or {}
            etag = res_headers.get("ETag") or res_headers.get("etag")
            last_modified = res_headers.get("Last-Modified") or res_headers.get(
                "last-modified"
            )
            if etag or last_modified:
                validator_entry: Dict[str, str] = {}
                if etag:
                    validator_entry["etag"] = etag
                if last_modified:
                    validator_entry["last_modified"] = last_modified
                _CONDITIONAL_VALIDATORS[self._validator_key()] = validator_entry
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
        status_code = getattr(res, "status", None) or getattr(res, "status_code", None)
        if self._event.config.conditional_request and status_code == 304:
            return FETCH_NOT_MODIFIED

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
