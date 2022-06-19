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
from fastapi import Depends, FastAPI, Header, HTTPException
from opal_common.fetcher import FetchingEngine
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig

# Configurable
PORT = int(os.environ.get("PORT") or "9110")
BASE_URL = f"http://localhost:{PORT}"
DATA_ROUTE = f"/data"
AUTHORIZED_DATA_ROUTE = f"/data_authz"
SECRET_TOKEN = "fake-super-secret-token"
DATA_KEY = "Hello"
DATA_VALUE = "World"
DATA_SECRET_VALUE = "SecretWorld"


async def check_token_header(x_token: str = Header(None)):
    if x_token != SECRET_TOKEN:
        raise HTTPException(status_code=400, detail="X-Token header invalid")
    return None


def setup_server():
    app = FastAPI()

    @app.get(DATA_ROUTE)
    def get_data():
        return {DATA_KEY: DATA_VALUE}

    @app.get(AUTHORIZED_DATA_ROUTE)
    def get_authorized_data(token=Depends(check_token_header)):
        return {DATA_KEY: DATA_SECRET_VALUE}

    uvicorn.run(app, port=PORT)


@pytest.fixture(scope="module")
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_simple_http_get(server):
    """Simple http get."""
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:

        async def callback(data):
            assert data[DATA_KEY] == DATA_VALUE
            got_data_event.set()

        await engine.queue_url(f"{BASE_URL}{DATA_ROUTE}", callback)
        await asyncio.wait_for(got_data_event.wait(), 5)
        assert got_data_event.is_set()


@pytest.mark.asyncio
async def test_simple_http_get_with_wait(server):
    """
    Simple http get - with 'queue_url_and_wait'
    """
    async with FetchingEngine() as engine:
        data = await engine.handle_url(f"{BASE_URL}{DATA_ROUTE}")
        assert data[DATA_KEY] == DATA_VALUE


@pytest.mark.asyncio
async def test_authorized_http_get(server):
    """Test getting data from a server route with an auth token."""
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:

        async def callback(data):
            assert data[DATA_KEY] == DATA_SECRET_VALUE
            got_data_event.set()

        # fetch with bearer token authorization
        await engine.queue_url(
            f"{BASE_URL}{AUTHORIZED_DATA_ROUTE}",
            callback,
            HttpFetcherConfig(headers={"X-TOKEN": SECRET_TOKEN}),
        )
        await asyncio.wait_for(got_data_event.wait(), 5)
        assert got_data_event.is_set()


@pytest.mark.asyncio
async def test_authorized_http_get_from_dict(server):
    """Just like test_authorized_http_get, but we also check that the
    FetcherConfig is adapted from "the wire" (as a dict instead of the explicit
    HttpFetcherConfig)"""
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:

        async def callback(data):
            assert data[DATA_KEY] == DATA_SECRET_VALUE
            got_data_event.set()

        # raw config to be parsed
        config = {"headers": {"X-TOKEN": SECRET_TOKEN}}
        # fetch with bearer token authorization
        await engine.queue_url(f"{BASE_URL}{AUTHORIZED_DATA_ROUTE}", callback, config)
        await asyncio.wait_for(got_data_event.wait(), 5)
        assert got_data_event.is_set()


@pytest.mark.asyncio
async def test_external_http_get():
    """Test simple http get on external (https://freegeoip.app/) site Checking
    we get a JSON with the data we expected (the IP we queried)"""
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:
        url = "https://httpbin.org/anything"

        async def callback(data):
            assert data["url"] == url
            got_data_event.set()

        await engine.queue_url(url, callback)
        await asyncio.wait_for(got_data_event.wait(), 5)
        assert got_data_event.is_set()
