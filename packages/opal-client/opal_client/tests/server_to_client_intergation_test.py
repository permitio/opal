import asyncio
import os
import sys
from multiprocessing import Event, Process

import pytest
import uvicorn
from aiohttp import ClientSession
from fastapi_websocket_pubsub import PubSubClient
from fastapi_websocket_rpc.logger import LoggingModes, logging_config

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)


from opal_client import OpalClient
from opal_client.data.rpc import TenantAwareRpcEventClientMethods
from opal_client.data.updater import DataSourceEntry, DataUpdate, DataUpdater
from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
from opal_client.policy_store.policy_store_client_factory import (
    PolicyStoreClientFactory,
)
from opal_client.policy_store.schemas import PolicyStoreTypes
from opal_common.schemas.data import DataSourceConfig, ServerDataSourceConfig
from opal_common.utils import get_authorization_header
from opal_server.config import opal_server_config
from opal_server.server import OpalServer

# Server settings
PORT = int(os.environ.get("PORT") or "9123")
UPDATES_URL = f"ws://localhost:{PORT}/ws"
DATA_ROUTE = "/fetchable_data"
DATA_URL = f"http://localhost:{PORT}{DATA_ROUTE}"
DATA_CONFIG_URL = f"http://localhost:{PORT}{opal_server_config.DATA_CONFIG_ROUTE}"
DATA_TOPICS = ["policy_data"]
TEST_DATA = {"hello": "world"}
DATA_SOURCES_CONFIG = ServerDataSourceConfig(
    config=DataSourceConfig(entries=[{"url": DATA_URL, "topics": DATA_TOPICS}])
)

# Client settings
CLIENT_PORT = int(os.environ.get("CLIENT_PORT") or "9321")
CLIENT_STORE_ROUTE = "/check_store"
CLIENT_STORE_URL = f"http://localhost:{CLIENT_PORT}{CLIENT_STORE_ROUTE}"


def setup_server(event):
    # Server without git watcher and with a test specifc url for data, and without broadcasting
    server = OpalServer(
        init_policy_watcher=False,
        init_publisher=False,
        data_sources_config=DATA_SOURCES_CONFIG,
        broadcaster_uri=None,
        enable_jwks_endpoint=False,
    )
    server_app = server.app

    # add a url to fetch data from
    @server_app.get(DATA_ROUTE)
    def fetchable_data():
        return TEST_DATA

    @server_app.on_event("startup")
    async def startup_event():
        await asyncio.sleep(0.2)
        # signal the server is ready
        event.set()

    uvicorn.run(server_app, port=PORT)


def setup_client(event):

    # config to use mock OPA
    policy_store = PolicyStoreClientFactory.create(store_type=PolicyStoreTypes.MOCK)
    data_updater = DataUpdater(
        pubsub_url=UPDATES_URL,
        data_sources_config_url=DATA_CONFIG_URL,
        policy_store=policy_store,
        fetch_on_connect=True,
        data_topics=DATA_TOPICS,
    )

    client = OpalClient(
        policy_store_type=PolicyStoreTypes.MOCK,
        policy_store=policy_store,
        data_updater=data_updater,
        policy_updater=False,
    )

    # add a url to fetch data from
    @client.app.get(CLIENT_STORE_ROUTE)
    async def get_store_data():
        # await asyncio.wait_for(client.policy_store.wait_for_data(),5)
        return await client.policy_store.get_data()

    @client.app.on_event("startup")
    async def startup_event():
        store: MockPolicyStoreClient = client.policy_store
        await store.wait_for_data()
        # signal the client is ready
        event.set()

    uvicorn.run(client.app, port=CLIENT_PORT)


@pytest.fixture(scope="module")
def server():
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(event,), daemon=True)
    proc.start()
    yield event
    proc.kill()  # Cleanup after test


@pytest.fixture(scope="module")
def client():
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_client, args=(event,), daemon=True)
    proc.start()
    yield event
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_client_connect_to_server_data_updates(client, server):
    """Disable auto-update on connect (fetch_on_connect=False) Connect to OPAL-
    server trigger a Data-update and check our policy store gets the update."""
    server.wait(5)
    client.wait(5)

    async with ClientSession() as session:
        res = await session.get(CLIENT_STORE_URL)
        data = await res.json()
        assert len(data) > 0
