"""Conditional data fetches (HttpFetcherConfig.conditional_requests): the
updater keeps the validators, skips the write on 304, and fetches in full when
the policy store lost the data, the validators expired, or the base data is
reloaded."""

import hashlib
import json
from typing import List
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from opal_client.config import opal_client_config
from opal_client.data.fetcher import DataFetcher
from opal_client.data.updater import DataUpdater
from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
from opal_common.config import opal_common_config
from opal_common.schemas.data import (
    DataEntryReport,
    DataSourceConfig,
    DataSourceEntry,
    DataUpdate,
)
from opal_common.schemas.store import StoreTransaction

TOPICS = ["policy_data"]


class _DataSource:
    """Serves ``body`` with an ETag and answers 304 to a matching If-None-
    Match."""

    def __init__(self):
        self.body = {"alice": {"role": "admin"}}
        self.requests: List[dict] = []

    @property
    def etag(self) -> str:
        return '"%s"' % hashlib.sha256(json.dumps(self.body).encode()).hexdigest()

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append(dict(request.headers))
        if request.headers.get("If-None-Match") == self.etag:
            return web.Response(status=304, headers={"ETag": self.etag})
        return web.json_response(self.body, headers={"ETag": self.etag})


class _RecordingStore(MockPolicyStoreClient):
    def __init__(self):
        super().__init__()
        self.writes = 0
        self.transactions: List[StoreTransaction] = []

    async def set_policy_data(self, policy_data, path="", transaction_id=None):
        self.writes += 1
        await super().set_policy_data(policy_data, path, transaction_id)

    async def log_transaction(self, transaction: StoreTransaction):
        self.transactions.append(transaction)


@pytest.fixture(params=["aiohttp", "httpx"])
def http_client(request, monkeypatch):
    monkeypatch.setattr(
        opal_common_config, "HTTP_FETCHER_PROVIDER_CLIENT", request.param
    )
    return request.param


@pytest_asyncio.fixture
async def source():
    data_source = _DataSource()
    app = web.Application()
    app.router.add_get("/data", data_source.handle)
    server = TestServer(app)
    await server.start_server()
    data_source.url = str(server.make_url("/data"))
    yield data_source
    await server.close()


@pytest_asyncio.fixture
async def setup(source, http_client):
    store = _RecordingStore()
    async with DataFetcher() as fetcher:
        updater = DataUpdater(
            token="fake-client-token",
            pubsub_url="ws://localhost:1/ws",
            data_sources_config_url="http://localhost:1/data/config",
            policy_store=store,
            data_fetcher=fetcher,
            data_topics=TOPICS,
            should_send_reports=False,
        )
        updater._send_reports = AsyncMock()
        yield updater, store, source


def _entry(source: _DataSource, conditional: bool = True) -> DataSourceEntry:
    return DataSourceEntry(
        url=source.url,
        config={"conditional_requests": conditional},
        topics=TOPICS,
        dst_path="/users",
    )


async def _update(updater: DataUpdater, entry: DataSourceEntry) -> DataEntryReport:
    await updater._update_policy_data(DataUpdate(entries=[entry]))
    reports = updater._send_reports.await_args.args[0]
    assert len(reports) == 1
    return reports[0]


@pytest.mark.asyncio
async def test_not_modified_keeps_the_stored_data(setup):
    updater, store, source = setup
    entry = _entry(source)

    first = await _update(updater, entry)
    second = await _update(updater, entry)

    assert "If-None-Match" not in source.requests[0]
    assert source.requests[1]["If-None-Match"] == source.etag
    assert store.writes == 1
    assert await store.get_data("/users") == source.body
    assert not first.not_modified
    assert second.not_modified
    assert second.fetched and second.saved
    assert second.hash == first.hash
    # a "not modified" is a successful transaction, so /healthy stays healthy
    assert [t.success for t in store.transactions] == [True, True]


@pytest.mark.asyncio
async def test_changed_data_is_saved(setup):
    updater, store, source = setup
    entry = _entry(source)

    await _update(updater, entry)
    source.body = {"bob": {"role": "viewer"}}
    report = await _update(updater, entry)

    assert not report.not_modified
    assert store.writes == 2
    assert await store.get_data("/users") == {"bob": {"role": "viewer"}}


@pytest.mark.asyncio
async def test_data_missing_from_the_store_is_fetched_in_full(setup):
    """An external policy store can restart and come back empty without the
    client noticing - a 304 must not leave it empty."""
    updater, store, source = setup
    entry = _entry(source)

    await _update(updater, entry)
    store._data.clear()
    report = await _update(updater, entry)

    # the conditional request got a 304, then the full fetch got the data
    assert source.requests[1]["If-None-Match"] == source.etag
    assert "If-None-Match" not in source.requests[2]
    assert not report.not_modified
    assert await store.get_data("/users") == source.body


@pytest.mark.asyncio
async def test_validators_expire_after_max_age(setup, monkeypatch):
    updater, store, source = setup
    monkeypatch.setattr(opal_client_config, "DATA_UPDATER_CONDITIONAL_FETCH_MAX_AGE", 0)
    entry = _entry(source)

    await _update(updater, entry)
    report = await _update(updater, entry)

    assert "If-None-Match" not in source.requests[1]
    assert not report.not_modified
    assert store.writes == 2


@pytest.mark.asyncio
async def test_base_data_load_clears_the_validators(setup):
    updater, store, source = setup
    entry = _entry(source)
    await _update(updater, entry)
    assert updater._conditional_fetch_states

    updater.get_policy_data_config = AsyncMock(
        return_value=DataSourceConfig(entries=[entry])
    )
    updater.trigger_data_update = AsyncMock()
    await updater.get_base_policy_data(data_fetch_reason="test")

    assert not updater._conditional_fetch_states


@pytest.mark.asyncio
async def test_validators_are_kept_per_config(setup):
    """Entries that differ only in config (e.g. auth headers) don't share
    validators."""
    updater, store, source = setup
    entry = _entry(source)
    other = DataSourceEntry(
        **{**entry.model_dump(), "config": {**entry.config, "headers": {"X": "1"}}}
    )

    await _update(updater, entry)
    await _update(updater, other)

    assert "If-None-Match" not in source.requests[1]


@pytest.mark.asyncio
async def test_off_by_default(setup):
    updater, store, source = setup
    entry = _entry(source, conditional=False)

    await _update(updater, entry)
    report = await _update(updater, entry)

    assert all("If-None-Match" not in headers for headers in source.requests)
    assert not report.not_modified
    assert store.writes == 2
    assert not updater._conditional_fetch_states
