

from opal_client.policy_store.policy_store_client_factory import PolicyStoreClientFactory
from opal_client.policy_store.schemas import PolicyStoreTypes
from opal_client.tests.data_updater_test import PATCH_DATA_UPDATE, DATA_TOPICS
import pytest
import asyncio
from opal_client.tests.test_provider.provider import TestFetcherConfig, TestFetchProvider
from opal_client.data.updater import DataSourceEntry, DataUpdate, DataUpdater
import os

from opal_common.schemas.store import JSONPatchAction

PORT = int(os.environ.get("PORT") or "9123")
UPDATES_URL = f"ws://localhost:{PORT}/ws"
DATA_ROUTE = "/fetchable_data"
DATA_URL = f"http://localhost:{PORT}{DATA_ROUTE}"
DATA_UPDATE_ROUTE = f"http://localhost:{PORT}/data/config"

DATA_UPDATE_1 = [JSONPatchAction(op="add", path="/", value={"user":"1"})]
DATA_UPDATE_2 = [JSONPatchAction(op="add", path="/", value={"user":"2"})]



entries = [
    DataSourceEntry(
        url="",
        data=PATCH_DATA_UPDATE,
        dst_path="test",
        topics=DATA_TOPICS,
        config =  {"fetcher":"TestsFetchProvider", "timeout": 10}
    ),
    DataSourceEntry(
        url="",
        data=PATCH_DATA_UPDATE,
        dst_path="test",
        topics=DATA_TOPICS,
        config = {"fetcher":"TestsFetchProvider", "timeout": 1}
    )
]


async def fetch_data(entry):
    policy_store = PolicyStoreClientFactory.create(store_type=PolicyStoreTypes.MOCK)
    updater = DataUpdater(
        pubsub_url=UPDATES_URL,
        policy_store=policy_store,
        fetch_on_connect=False,
        data_topics=DATA_TOPICS,
        should_send_reports=False,
    )

    await updater.trigger_data_update(
            update=DataUpdate(
                entries=[entry],
                reason="test",
            )
        )


@pytest.mark.asyncio
async def test_race():
    await fetch_data(entries[0])
    await asyncio.sleep(3)
    await fetch_data(entries[1])


