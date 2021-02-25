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
from fastapi import FastAPI

from opal.fetcher import FetchingEngine, FetchEvent

# Configurable
PORT = int(os.environ.get("PORT") or "9110")
BASE_URL = f"http://localhost:{PORT}"
DATA_ROUTE = f"/data"
DATA_KEY = "Hello"
DATA_VALUE = "World"
DATA_SECRET_VALUE = "SecretWorld"


def setup_server():
    app =  FastAPI()

    @app.get(DATA_ROUTE)
    def get_data():
        return {DATA_KEY: DATA_VALUE}

    uvicorn.run(app, port=PORT )

@pytest.fixture(scope="module")
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill() # Cleanup after test

@pytest.mark.asyncio
async def test_retry_failure(server):
    """
    Test callback on failure
    """
    got_data_event = asyncio.Event()
    got_error = asyncio.Event()
    
    async with FetchingEngine() as engine:
        
        async def error_callback(error:Exception, event:FetchEvent):
            got_error.set()

        engine.register_failure_handler(error_callback)

        async def callback(result):
            data = result.json()
            assert data[DATA_KEY] == DATA_VALUE
            got_data_event.set()

        await engine.queue_url(f"{BASE_URL}/wrongroute", callback)
        await asyncio.wait_for(got_error.wait(), 5)
        assert not got_data_event.is_set()
        assert not got_error.is_set()
