"""Simple HTTP get data fetcher using requests supports."""

from fastapi_websocket_rpc.rpc_methods import RpcMethodsBase
from fastapi_websocket_rpc.websocket_rpc_client import WebSocketRpcClient

from ..events import FetcherConfig, FetchEvent
from ..fetch_provider import BaseFetchProvider
from ..logger import get_logger

logger = get_logger("rpc_fetch_provider")


class FastApiRpcFetchConfig(FetcherConfig):
    """Config for FastApiRpcFetchConfig's Adding HTTP headers."""

    rpc_method_name: str
    rpc_arguments: dict


class FastApiRpcFetchEvent(FetchEvent):
    fetcher: str = "FastApiRpcFetchProvider"
    config: FastApiRpcFetchConfig


class FastApiRpcFetchProvider(BaseFetchProvider):
    def __init__(self, event: FastApiRpcFetchEvent) -> None:
        self._event: FastApiRpcFetchEvent
        super().__init__(event)

    def parse_event(self, event: FetchEvent) -> FastApiRpcFetchEvent:
        return FastApiRpcFetchEvent(
            **event.dict(exclude={"config"}), config=event.config
        )

    async def _fetch_(self):
        assert (
            self._event is not None
        ), "FastApiRpcFetchEvent not provided for FastApiRpcFetchProvider"
        args = self._event.config.rpc_arguments
        method = self._event.config.rpc_method_name
        result = None
        logger.info(
            f"{self.__class__.__name__} fetching from {self._url} with RPC call {method}({args})"
        )
        async with WebSocketRpcClient(
            self._url,
            # we don't expose anything to the server
            RpcMethodsBase(),
            default_response_timeout=4,
        ) as client:
            result = await client.call(method, args)
        return result
