"""Data update notifications and saves are logged without the update's fetcher
auth headers or credentialed source urls."""

import asyncio
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from opal_client.data.rpc import TenantAwareRpcEventClientMethods
from opal_client.data.updater import DataUpdater
from opal_client.limiter import StartupLoadLimiter
from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
from opal_common.schemas.data import DataSourceEntry, DataUpdate
from opal_common.schemas.store import StoreTransaction
from opal_common.tests.redaction_fixtures import capture_logs
from tenacity import stop_after_attempt

FAKE_KEY = "FAKE-KEY-123"
CLIENT_TOKEN = "fake-client-token"
CREDENTIALED_URL = f"https://user:{FAKE_KEY}@data.example.com/users?token={FAKE_KEY}"
UPDATE = {
    "entries": [
        {
            "url": CREDENTIALED_URL,
            "config": {"headers": {"Authorization": f"Bearer {FAKE_KEY}"}},
            "topics": ["policy_data"],
        }
    ],
    "reason": "test",
}


@pytest.mark.asyncio
async def test_update_notification_log_omits_update_contents():
    client = MagicMock()
    client.trigger_topic = AsyncMock()
    methods = TenantAwareRpcEventClientMethods(client)

    with capture_logs() as logs:
        await methods.notify(subscription={"topic": "tenant::policy_data"}, data=UPDATE)

    assert "Received notification of event: tenant::policy_data" in logs.combined
    assert FAKE_KEY not in logs.combined
    # the update itself is still passed on in full
    client.trigger_topic.assert_awaited_once_with(topic="policy_data", data=UPDATE)


@pytest.mark.asyncio
async def test_data_save_log_redacts_source_url():
    store = MockPolicyStoreClient()
    fetcher = MagicMock()
    fetcher.handle_url = AsyncMock(return_value={"alice": {"role": "admin"}})
    updater = DataUpdater(
        token=CLIENT_TOKEN,
        pubsub_url="ws://localhost:1/ws",
        data_sources_config_url="http://localhost:1/data/config",
        policy_store=store,
        data_fetcher=fetcher,
        data_topics=["policy_data"],
        should_send_reports=False,
    )
    update = DataUpdate(
        entries=[
            DataSourceEntry(
                url=CREDENTIALED_URL, topics=["policy_data"], dst_path="/users"
            )
        ]
    )

    with capture_logs() as logs:
        await updater.trigger_data_update(update)
        await asyncio.wait_for(store.has_data_event.wait(), timeout=5)

    assert (
        "Saving fetched data to policy-store: source url="
        "'https://***@data.example.com/users?token=***'"
    ) in logs.combined
    assert FAKE_KEY not in logs.combined
    assert await store.get_data("/users") == {"alice": {"role": "admin"}}


class _RecordingStore(MockPolicyStoreClient):
    def __init__(self, save_error: Optional[Exception] = None):
        super().__init__()
        self.transactions: List[StoreTransaction] = []
        self.transaction_logged = asyncio.Event()
        self._save_error = save_error

    async def set_policy_data(self, policy_data, path="", transaction_id=None):
        if self._save_error is not None:
            raise self._save_error
        await super().set_policy_data(policy_data, path, transaction_id)

    async def log_transaction(self, transaction: StoreTransaction):
        self.transactions.append(transaction)
        self.transaction_logged.set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fetch_error,save_error,expected",
    [
        (
            TimeoutError(),
            None,
            "Exception: Failed to fetch data for entry "
            "https://***@data.example.com/users?token=***: TimeoutError",
        ),
        (None, TimeoutError(), "Failed to save data to policy store: TimeoutError"),
    ],
    ids=["fetch", "save"],
)
async def test_stored_data_error_names_an_exception_without_a_message(
    fetch_error, save_error, expected
):
    """str() of a TimeoutError is empty, which left the stored error ending in
    ": " - the transaction recorded no cause at all."""
    store = _RecordingStore(save_error=save_error)
    fetcher = MagicMock()
    if fetch_error is not None:
        fetcher.handle_url = AsyncMock(side_effect=fetch_error)
    else:
        fetcher.handle_url = AsyncMock(return_value={"alice": {"role": "admin"}})
    updater = DataUpdater(
        token=CLIENT_TOKEN,
        pubsub_url="ws://localhost:1/ws",
        data_sources_config_url="http://localhost:1/data/config",
        policy_store=store,
        data_fetcher=fetcher,
        data_topics=["policy_data"],
        should_send_reports=False,
    )
    update = DataUpdate(
        entries=[
            DataSourceEntry(
                url=CREDENTIALED_URL, topics=["policy_data"], dst_path="/users"
            )
        ]
    )

    await updater.trigger_data_update(update)
    await asyncio.wait_for(store.transaction_logged.wait(), timeout=5)

    (transaction,) = store.transactions
    (remote,) = transaction.remotes_status
    assert remote.error == expected
    assert FAKE_KEY not in transaction.model_dump_json()


async def _redirect_loop(request: web.Request) -> web.Response:
    raise web.HTTPFound(request.path)


@pytest.mark.asyncio
async def test_load_limiter_connection_error_log_omits_client_token():
    app = web.Application()
    app.router.add_get("/loadlimit", _redirect_loop)
    async with TestServer(app) as server:
        limiter = StartupLoadLimiter(
            backend_url=str(server.make_url("")).rstrip("/"), token=CLIENT_TOKEN
        )
        wait_once = limiter.wait_for_server_ready.retry_with(stop=stop_after_attempt(1))
        with capture_logs() as logs:
            with pytest.raises(Exception) as exc_info:
                await wait_once(limiter)

    assert CLIENT_TOKEN in repr(exc_info.value)  # what the log line must not render
    assert "server connection error: TooManyRedirects" in logs.combined
    assert CLIENT_TOKEN not in logs.combined
