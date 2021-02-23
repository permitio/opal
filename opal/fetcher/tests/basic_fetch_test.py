import logging
import os
import sys

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(os.path.join(os.path.basename(__file__), os.path.pardir))
print (root_dir)
sys.path.append(root_dir)

import asyncio
from multiprocessing import Process

import pytest
import uvicorn
from fastapi import FastAPI

from opal.fetcher import FetchingEngine


# Configurable
PORT = int(os.environ.get("PORT") or "9000")
URL = f"ws://localhost:{PORT}/data"


def setup_server():
    app =  FastAPI()

    @app.get("/data")
    def get_data():
        return {"Hello": "World"}

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
    """
    engine = FetchingEngine()
    got_data_event = asyncio.Event()
    
    async def callback(data):
        assert data["Hello"] == "World"
        got_data_event.set()
    engine.handle_url(URL, callback)
    await asyncio.wait_for(got_data_event.wait(), 5)
    assert got_data_event.is_set()
