import os
import sys


# Add parent path to use local src as package for tests
root_dir = os.path.abspath(os.path.join(os.path.basename(__file__), os.path.pardir))
sys.path.append(root_dir)

import asyncio
import pytest
import uvicorn


from opal.client.data.updater import DataUpdater
from opal.client.policy_store.policy_store_client_factory import PolicyStoreTypes, PolicyStoreClientFactory


@pytest.mark.asyncio
async def test_client_data_updates(server):
    # config to use mock OPA
    policy_store = PolicyStoreClientFactory.create()
    updater = DataUpdater()
    