
import os
import sys
import logging

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(os.path.join(os.path.basename(__file__), os.path.pardir))
sys.path.append(root_dir)

import asyncio
from multiprocessing import Process, Event
from aiohttp_requests import requests
import pytest
import uvicorn
from fastapi_websocket_pubsub import PubSubClient

PORT = int(os.environ.get("PORT") or "9123")
UPDATES_URL = f"ws://localhost:{PORT}/ws"
DATA_ROUTE = "/fetchable_data"
TRIGGER_ROUTE = "/fetchable_data"
DATA_URL = f"http://localhost:{PORT}{DATA_ROUTE}"
TRIGGER_URL = f"http://localhost:{PORT}{TRIGGER_ROUTE}"
DATA_TOPICS = ["policy_data"]
TEST_DATA = {
    "hello": "world"
}

from opal.client import config
from opal.client.data.updater import DataUpdater, DataUpdate, DataUpdateEntry
from opal.client.policy_store import PolicyStoreTypes, PolicyStoreClientFactory, MockPolicyStoreClient
from opal.server.main import app as server_app
from opal.server.pubsub.websocket import endpoint
from opal.client.utils import get_authorization_header
from opal.client.data.rpc import TenantAwareRpcEventClientMethods

def setup_server(event):
    # add a url to fetch data from  
    @server_app.get(DATA_ROUTE)
    def fetchable_data():
        return TEST_DATA

    @server_app.post(TRIGGER_ROUTE)
    async def trigger_data_update(update:DataUpdate):
        asyncio.create_task(endpoint.publish(DATA_TOPICS, data=update))
        logging.info("published")

    @server_app.on_event("startup")
    async def startup_event():
        #signal the server is ready
        event.set()
        
    uvicorn.run(server_app, port=PORT)

@pytest.fixture(scope="module")
def server():
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(event,), daemon=True)
    proc.start()
    yield event
    proc.kill() # Cleanup after test

@pytest.mark.asyncio
async def test_client_data_updates(server):
    # Wait for the server to start
    server.wait(5)
    # config to use mock OPA
    policy_store = PolicyStoreClientFactory.create(store_type=PolicyStoreTypes.MOCK)
    updater = DataUpdater(server_url=UPDATES_URL, policy_store=policy_store, fetch_on_connect=False, data_topics=DATA_TOPICS)
    # start the updater (terminate on exit)
    updater.start()
    try:
        # trigger an update
        entries= [DataUpdateEntry(url=DATA_URL)]
        update = DataUpdate(reason="Test", entries=entries)
        async with PubSubClient(
            server_uri=UPDATES_URL,
            methods_class=TenantAwareRpcEventClientMethods,
            extra_headers=[get_authorization_header(config.CLIENT_TOKEN)]
        ) as client:
            # Channel must be ready before we can publish on it
            await asyncio.wait_for(client.wait_until_ready(),5)
            await client.publish(DATA_TOPICS,data=update)
        # wait until new data arrives into the strore via the updater
        await asyncio.wait_for(policy_store.wait_for_data(),25)
        
    #cleanup
    finally:
        pass
        #doesn't work due to separate thread loops
        # await updater.stop()


    