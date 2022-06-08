import os
import sys

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), os.path.pardir, os.path.pardir, os.path.pardir
    )
)
sys.path.append(root_dir)

import asyncio
from multiprocessing import Process

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi_websocket_rpc import RpcMethodsBase, WebsocketRPCEndpoint
from opal_common.fetcher import FetchingEngine
from opal_common.fetcher.providers.fastapi_rpc_fetch_provider import (
    FastApiRpcFetchConfig,
    FastApiRpcFetchEvent,
    FastApiRpcFetchProvider,
)

# Configurable
PORT = int(os.environ.get("PORT") or "9110")
uri = f"ws://localhost:{PORT}/rpc"
DATA_PREFIX = "I AM DATA - HEAR ME ROAR"
SUFFIX = " - Magic!"


class RpcData(RpcMethodsBase):
    async def get_data(self, suffix: str) -> str:
        return DATA_PREFIX + suffix


def setup_server():
    app = FastAPI()
    endpoint = WebsocketRPCEndpoint(RpcData())
    endpoint.register_route(app, "/rpc")

    uvicorn.run(app, port=PORT)


@pytest.fixture(scope="module")
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_simple_rpc_fetch(server):
    """"""
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:
        engine.register.register_fetcher(
            FastApiRpcFetchProvider.__name__, FastApiRpcFetchProvider
        )
        # Event for RPC fetch
        fetch_event = FastApiRpcFetchEvent(
            url=uri,
            config=FastApiRpcFetchConfig(
                rpc_method_name="get_data", rpc_arguments={"suffix": SUFFIX}
            ),
        )
        # Callback for event
        async def callback(result):
            data = result.result
            assert data == DATA_PREFIX + SUFFIX
            got_data_event.set()

        await engine.queue_fetch_event(fetch_event, callback)
        await asyncio.wait_for(got_data_event.wait(), 5)
        assert got_data_event.is_set()
