import os
import sys

import aiohttp

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), os.path.pardir, os.path.pardir, os.path.pardir
    )
)
print(root_dir)
sys.path.append(root_dir)

import asyncio

import pytest
import tenacity
from opal_common.fetcher import FetchEvent, FetchingEngine
from opal_common.fetcher.providers.http_fetch_provider import (
    HttpFetchEvent,
    HttpFetchProvider,
)

# Configurable
PORT = int(os.environ.get("PORT") or "9110")
BASE_URL = f"http://localhost:{PORT}"
DATA_ROUTE = f"/data"
DATA_KEY = "Hello"
DATA_VALUE = "World"
DATA_SECRET_VALUE = "SecretWorld"


@pytest.mark.asyncio
async def test_retry_failure():
    """Test callback on failure."""
    got_data_event = asyncio.Event()
    got_error = asyncio.Event()

    async with FetchingEngine() as engine:
        # callback to handle failure
        async def error_callback(error: Exception, event: FetchEvent):
            # check we got the expection we expected
            assert isinstance(error, aiohttp.client_exceptions.ClientConnectorError)
            got_error.set()

        # register the callback
        engine.register_failure_handler(error_callback)
        # callback for success - shouldn't eb called in this test
        async def callback(result):
            got_data_event.set()

        # Use an event on an invalid port - and only to attempts
        retry_config = HttpFetchProvider.DEFAULT_RETRY_CONFIG.copy()
        retry_config["stop"] = tenacity.stop.stop_after_attempt(2)
        event = HttpFetchEvent(url=f"http://localhost:25", retry=retry_config)
        # queue the event
        await engine.queue_fetch_event(event, callback)
        # wait for the failure callback
        await asyncio.wait_for(got_error.wait(), 25)
        assert not got_data_event.is_set()
        assert got_error.is_set()
