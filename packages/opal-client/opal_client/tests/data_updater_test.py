import asyncio
import json
import logging
import multiprocessing
import os
import sys
from multiprocessing import Event, Process

import pytest
import requests
import uvicorn
from aiohttp import ClientSession
from fastapi_websocket_pubsub import PubSubClient
from pydantic.json import pydantic_encoder

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from opal_client.config import opal_client_config
from opal_client.data.rpc import TenantAwareRpcEventClientMethods
from opal_client.data.updater import DataSourceEntry, DataUpdate, DataUpdater
from opal_client.policy_store.policy_store_client_factory import (
    PolicyStoreClientFactory,
)
from opal_client.policy_store.schemas import PolicyStoreTypes
from opal_common.schemas.data import (
    DataSourceConfig,
    DataUpdateReport,
    ServerDataSourceConfig,
    UpdateCallback,
)
from opal_common.schemas.store import JSONPatchAction
from opal_common.tests.test_utils import wait_for_server
from opal_common.utils import get_authorization_header
from opal_server.config import opal_server_config
from opal_server.server import OpalServer

PORT = int(os.environ.get("PORT") or "9123")
UPDATES_URL = f"ws://localhost:{PORT}/ws"
DATA_ROUTE = "/fetchable_data"
DATA_URL = f"http://localhost:{PORT}{DATA_ROUTE}"
DATA_CONFIG_URL = f"http://localhost:{PORT}{opal_server_config.DATA_CONFIG_ROUTE}"
DATA_TOPICS = ["policy_data"]
TEST_DATA = {"hello": "world"}

DATA_UPDATE_CALLBACK_ROUTE = "/data/callback_report_for_test"
DATA_UPDATE_CALLBACK_URL = f"http://localhost:{PORT}{DATA_UPDATE_CALLBACK_ROUTE}"

CHECK_DATA_UPDATE_CALLBACK_ROUTE = "/callback_count"
CHECK_DATA_UPDATE_CALLBACK_URL = (
    f"http://localhost:{PORT}{CHECK_DATA_UPDATE_CALLBACK_ROUTE}"
)

DATA_SOURCES_CONFIG = ServerDataSourceConfig(
    config=DataSourceConfig(entries=[{"url": DATA_URL, "topics": DATA_TOPICS}])
)
DATA_UPDATE_ROUTE = f"http://localhost:{PORT}/data/config"

PATCH_DATA_UPDATE = [JSONPatchAction(op="add", path="/", value=TEST_DATA)]


def setup_server(event):
    # Server without git watcher and with a test specific url for data, and without broadcasting
    server = OpalServer(
        init_policy_watcher=False,
        data_sources_config=DATA_SOURCES_CONFIG,
        broadcaster_uri=None,
        enable_jwks_endpoint=False,
    )
    server_app = server.app

    callbacks = []

    # add a url to fetch data from
    @server_app.get(DATA_ROUTE)
    def fetchable_data():
        return TEST_DATA

    # route to report complition to
    @server_app.post(DATA_UPDATE_CALLBACK_ROUTE)
    def callback(report: DataUpdateReport):
        if len(callbacks) == 1:
            assert report.reports[0].hash == DataUpdater.calc_hash(PATCH_DATA_UPDATE)
        else:
            assert report.reports[0].hash == DataUpdater.calc_hash(TEST_DATA)
        callbacks.append(report)
        return "OKAY"

    # route to report complition to
    @server_app.get(CHECK_DATA_UPDATE_CALLBACK_ROUTE)
    def check() -> int:
        return len(callbacks)

    @server_app.on_event("startup")
    async def startup_event():
        # signal the server is ready
        event.set()

    uvicorn.run(server_app, port=PORT)


@pytest.fixture(scope="module")
def server():
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(event,), daemon=True)
    proc.start()
    assert event.wait(5)
    wait_for_server(PORT)
    yield event
    proc.kill()  # Cleanup after test


def trigger_update():
    async def run():
        # trigger an update
        entries = [DataSourceEntry(url=DATA_URL, topics=DATA_TOPICS)]
        callback = UpdateCallback(callbacks=[DATA_UPDATE_CALLBACK_URL])
        update = DataUpdate(reason="Test", entries=entries, callback=callback)
        async with PubSubClient(
            server_uri=UPDATES_URL,
            methods_class=TenantAwareRpcEventClientMethods,
            extra_headers=[get_authorization_header(opal_client_config.CLIENT_TOKEN)],
        ) as client:
            # Channel must be ready before we can publish on it
            await asyncio.wait_for(client.wait_until_ready(), 5)
            logging.info("Publishing data event")
            await client.publish(DATA_TOPICS, data=update)

    asyncio.run(run())


def trigger_update_patch():
    async def run():
        # trigger an update
        entries = [
            DataSourceEntry(
                url="",
                data=PATCH_DATA_UPDATE,
                dst_path="/",
                save_method="PATCH",
                topics=DATA_TOPICS,
            )
        ]
        callback = UpdateCallback(callbacks=[DATA_UPDATE_CALLBACK_URL])
        update = DataUpdate(reason="Test", entries=entries, callback=callback)
        async with PubSubClient(
            server_uri=UPDATES_URL,
            methods_class=TenantAwareRpcEventClientMethods,
            extra_headers=[get_authorization_header(opal_client_config.CLIENT_TOKEN)],
        ) as client:
            # Channel must be ready before we can publish on it
            await asyncio.wait_for(client.wait_until_ready(), 5)
            logging.info("Publishing data event")
            await client.publish(DATA_TOPICS, data=update)

    asyncio.run(run())


@pytest.mark.flaky(reruns=1)
@pytest.mark.asyncio
async def test_data_updater(server):
    """Disable auto-update on connect (fetch_on_connect=False) Connect to OPAL-
    server trigger a Data-update and check our policy store gets the update."""
    # config to use mock OPA
    policy_store = PolicyStoreClientFactory.create(store_type=PolicyStoreTypes.MOCK)
    updater = DataUpdater(
        pubsub_url=UPDATES_URL,
        policy_store=policy_store,
        fetch_on_connect=False,
        data_topics=DATA_TOPICS,
        should_send_reports=False,
    )
    # start the updater (terminate on exit)
    await updater.start()
    try:
        proc = multiprocessing.Process(target=trigger_update, daemon=True)
        proc.start()
        # wait until new data arrives into the store via the updater
        await asyncio.wait_for(policy_store.wait_for_data(), 60)
    # cleanup
    finally:
        await updater.stop()
        proc.terminate()
    try:
        proc = multiprocessing.Process(target=trigger_update_patch, daemon=True)
        proc.start()
        # wait until new data arrives into the store via the updater
        await asyncio.wait_for(policy_store.wait_for_data(), 60)
    # cleanup
    finally:
        await updater.stop()
        proc.terminate()

    # test PATCH update event via API
    entries = [
        DataSourceEntry(
            url="",
            data=PATCH_DATA_UPDATE,
            dst_path="/",
            topics=DATA_TOPICS,
            save_method="PATCH",
        )
    ]
    update = DataUpdate(
        reason="Test_Patch", entries=entries, callback=UpdateCallback(callbacks=[])
    )

    headers = {"content-type": "application/json"}
    # trigger an update
    res = requests.post(
        DATA_UPDATE_ROUTE,
        data=json.dumps(update, default=pydantic_encoder),
        headers=headers,
    )
    assert res.status_code == 200
    # value field is not specified for add operation should fail
    entries[0].data = [{"op": "add", "path": "/"}]
    res = requests.post(
        DATA_UPDATE_ROUTE,
        data=json.dumps(update, default=pydantic_encoder),
        headers=headers,
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_data_updater_with_report_callback(server):
    """Disable auto-update on connect (fetch_on_connect=False) Connect to OPAL-
    server trigger a Data-update and check our policy store gets the update."""
    # config to use mock OPA
    policy_store = PolicyStoreClientFactory.create(store_type=PolicyStoreTypes.MOCK)
    updater = DataUpdater(
        pubsub_url=UPDATES_URL,
        policy_store=policy_store,
        fetch_on_connect=False,
        data_topics=DATA_TOPICS,
        should_send_reports=True,
    )
    # start the updater (terminate on exit)
    await updater.start()

    current_callback_count = 0
    async with ClientSession() as session:
        res = await session.get(CHECK_DATA_UPDATE_CALLBACK_URL)
        current_callback_count = await res.json()

    proc2 = None
    try:
        proc = multiprocessing.Process(target=trigger_update, daemon=True)
        proc.start()
        # wait until new data arrives into the store via the updater
        await asyncio.wait_for(policy_store.wait_for_data(), 15)
        # give the callback a chance to arrive
        await asyncio.sleep(1)

        async with ClientSession() as session:
            res = await session.get(CHECK_DATA_UPDATE_CALLBACK_URL)
            count = await res.json()
            # we got one callback in the interim
            assert count == current_callback_count + 1

        async with ClientSession() as session:
            res = await session.get(CHECK_DATA_UPDATE_CALLBACK_URL)
            current_callback_count = await res.json()

        proc2 = multiprocessing.Process(target=trigger_update_patch, daemon=True)
        proc2.start()
        # wait until new data arrives into the store via the updater
        await asyncio.wait_for(policy_store.wait_for_data(), 15)
        # give the callback a chance to arrive
        await asyncio.sleep(1)

        async with ClientSession() as session:
            res = await session.get(CHECK_DATA_UPDATE_CALLBACK_URL)
            count = await res.json()
            # we got one callback in the interim
            assert count == current_callback_count + 1

    # cleanup
    finally:
        await updater.stop()
        proc.terminate()
        if proc2:
            proc2.terminate()


@pytest.mark.asyncio
async def test_client_get_initial_data(server):
    """Connect to OPAL-server and make sure data is fetched on-connect."""
    # config to use mock OPA
    policy_store = PolicyStoreClientFactory.create(store_type=PolicyStoreTypes.MOCK)
    updater = DataUpdater(
        pubsub_url=UPDATES_URL,
        data_sources_config_url=DATA_CONFIG_URL,
        policy_store=policy_store,
        fetch_on_connect=True,
        data_topics=DATA_TOPICS,
        should_send_reports=False,
    )
    # start the updater (terminate on exit)
    await updater.start()
    try:
        # wait until new data arrives into the store via the updater
        await asyncio.wait_for(policy_store.wait_for_data(), 5)
    # cleanup
    finally:
        await updater.stop()
