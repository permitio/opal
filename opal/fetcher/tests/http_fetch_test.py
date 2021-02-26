import logging
import os
import sys

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(os.path.join(os.path.basename(__file__), os.path.pardir))
sys.path.append(root_dir)

import asyncio
from multiprocessing import Process

import pytest
import uvicorn
from fastapi import FastAPI, Depends, Header, HTTPException

from opal.fetcher import FetchingEngine
from opal.fetcher.providers.http_get_fetch_provider import HttpGetFetcherConfig


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
    app =  FastAPI()

    @app.get(DATA_ROUTE)
    def get_data():
        return {DATA_KEY: DATA_VALUE}

    @app.get(AUTHORIZED_DATA_ROUTE)
    def get_authorized_data(token=Depends(check_token_header)):
        return {DATA_KEY: DATA_SECRET_VALUE}

    uvicorn.run(app, port=PORT )

@pytest.fixture(scope="module")
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill() # Cleanup after test

@pytest.mark.asyncio
async def test_simple_http_get(server):
    """
    Simple http get
    """
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:
        async def callback(result):
            data = await result.json()
            assert data[DATA_KEY] == DATA_VALUE
            got_data_event.set()
        await engine.queue_url(f"{BASE_URL}{DATA_ROUTE}", callback)
        await asyncio.wait_for(got_data_event.wait(), 10)
        assert got_data_event.is_set()

@pytest.mark.asyncio
async def test_authorized_http_get(server):
    """
    Test getting from a server route with an auth token
    """
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:
        async def callback(result):
            data = await result.json()
            assert data[DATA_KEY] == DATA_SECRET_VALUE
            got_data_event.set()
        # fetch with bearer token authorization 
        await engine.queue_url(f"{BASE_URL}{AUTHORIZED_DATA_ROUTE}", callback, HttpGetFetcherConfig(headers={"X-TOKEN": SECRET_TOKEN}))
        await asyncio.wait_for(got_data_event.wait(), 15)
        assert got_data_event.is_set()


@pytest.mark.asyncio
async def test_external_http_get():
    """
    Test simple http get on external (https://freegeoip.app/) site
    Checking we get a JSON with the data we expected (the IP we queried)
    """
    got_data_event = asyncio.Event()
    async with FetchingEngine() as engine:
        async def callback(result):
            data = await result.json()
            assert data["ip"] == "8.8.8.8"
            got_data_event.set()
        await engine.queue_url(f"https://freegeoip.app/json/8.8.8.8", callback)
        await asyncio.wait_for(got_data_event.wait(), 5)
        assert got_data_event.is_set()        
