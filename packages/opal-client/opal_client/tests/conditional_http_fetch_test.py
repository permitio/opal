"""Tests for opt-in HTTP conditional requests (ETag / If-None-Match / Last-
Modified / If-Modified-Since -> 304 Not Modified) in HttpFetchProvider and
DataUpdater (issue #990)."""

import asyncio
from typing import Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from opal_client.data.fetcher import DataFetcher
from opal_client.data.updater import DataUpdater
from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
from opal_common.config import opal_common_config
from opal_common.fetcher import FetchingEngine
from opal_common.fetcher.providers.http_fetch_provider import (
    FETCH_NOT_MODIFIED,
    HttpFetcherConfig,
    clear_conditional_validators,
)
from opal_common.schemas.data import DataSourceConfig, DataSourceEntry, DataUpdate
from opal_common.schemas.store import StoreTransaction, TransactionType


class _RecordingPolicyStore(MockPolicyStoreClient):
    def __init__(self):
        super().__init__()
        self.write_calls: List[tuple] = []
        self.transactions: List[StoreTransaction] = []
        self.transaction_event = asyncio.Event()

    async def set_policy_data(self, policy_data, path="", transaction_id=None):
        self.write_calls.append((path, policy_data))
        await super().set_policy_data(policy_data, path, transaction_id)

    async def log_transaction(self, transaction: StoreTransaction):
        self.transactions.append(transaction)
        self.transaction_event.set()


def _make_conditional_app(state: Dict):
    app = web.Application()

    async def handle_data(request: web.Request) -> web.Response:
        state["requests"].append(dict(request.headers))
        inm = request.headers.get("If-None-Match")
        ims = request.headers.get("If-Modified-Since")
        if (inm and inm == state.get("etag")) or (
            ims and ims == state.get("last_modified")
        ):
            return web.Response(
                status=304,
                headers={
                    k: v
                    for k, v in {
                        "ETag": state.get("etag"),
                        "Last-Modified": state.get("last_modified"),
                    }.items()
                    if v
                },
            )
        headers = {}
        if state.get("etag"):
            headers["ETag"] = state["etag"]
        if state.get("last_modified"):
            headers["Last-Modified"] = state["last_modified"]
        return web.json_response(state["payload"], headers=headers)

    async def handle_config(request: web.Request) -> web.Response:
        return web.json_response(state["config"])

    app.router.add_get("/data", handle_data)
    app.router.add_get("/data/config", handle_config)
    return app


@pytest.fixture(autouse=True)
def _reset_validators():
    clear_conditional_validators()
    yield
    clear_conditional_validators()


@pytest.mark.asyncio
@pytest.mark.parametrize("client_backend", ["aiohttp", "httpx"])
async def test_http_fetch_provider_conditional_etag_and_last_modified(
    monkeypatch, client_backend
):
    monkeypatch.setattr(
        opal_common_config, "HTTP_FETCHER_PROVIDER_CLIENT", client_backend
    )
    state = {
        "etag": '"v1-etag"',
        "last_modified": "Wed, 21 Oct 2026 07:28:00 GMT",
        "payload": {"users": ["alice"]},
        "requests": [],
    }
    async with TestServer(_make_conditional_app(state)) as server:
        url = str(server.make_url("/data"))
        cfg = HttpFetcherConfig(conditional_request=True)

        async with FetchingEngine(worker_count=1) as engine:
            first = await engine.handle_url(url, config=cfg)
            assert first == {"users": ["alice"]}
            assert "If-None-Match" not in state["requests"][0]

            second = await engine.handle_url(url, config=cfg)
            assert second is FETCH_NOT_MODIFIED
            assert state["requests"][1].get("If-None-Match") == '"v1-etag"'
            assert (
                state["requests"][1].get("If-Modified-Since")
                == "Wed, 21 Oct 2026 07:28:00 GMT"
            )

            # Rotate ETag and payload -> next conditional request gets 200 OK with new data
            state["etag"] = '"v2-etag"'
            state["last_modified"] = "Thu, 22 Oct 2026 07:28:00 GMT"
            state["payload"] = {"users": ["alice", "bob"]}

            third = await engine.handle_url(url, config=cfg)
            assert third == {"users": ["alice", "bob"]}
            assert state["requests"][2].get("If-None-Match") == '"v1-etag"'

            fourth = await engine.handle_url(url, config=cfg)
            assert fourth is FETCH_NOT_MODIFIED
            assert state["requests"][3].get("If-None-Match") == '"v2-etag"'


@pytest.mark.asyncio
async def test_http_fetch_provider_default_disabled_does_not_send_validators():
    state = {
        "etag": '"v1-etag"',
        "last_modified": None,
        "payload": {"users": ["alice"]},
        "requests": [],
    }
    async with TestServer(_make_conditional_app(state)) as server:
        url = str(server.make_url("/data"))
        async with FetchingEngine(worker_count=1) as engine:
            first = await engine.handle_url(url, config=HttpFetcherConfig())
            second = await engine.handle_url(url, config=HttpFetcherConfig())
            assert first == {"users": ["alice"]}
            assert second == {"users": ["alice"]}
            assert "If-None-Match" not in state["requests"][1]


@pytest.mark.asyncio
async def test_data_updater_skips_store_write_on_304_and_clears_on_base_fetch():
    state = {
        "etag": '"etag-100"',
        "last_modified": None,
        "payload": {"roles": {"admin": True}},
        "requests": [],
        "config": {},
    }
    async with TestServer(_make_conditional_app(state)) as server:
        data_url = str(server.make_url("/data"))
        config_url = str(server.make_url("/data/config"))
        entry = DataSourceEntry(
            url=data_url,
            dst_path="/roles",
            topics=["policy_data"],
            config={"conditional_request": True},
        )
        state["config"] = DataSourceConfig(entries=[entry]).model_dump()

        store = _RecordingPolicyStore()
        fetcher = DataFetcher()
        await fetcher.start()
        updater = DataUpdater(
            token="test-token",
            pubsub_url="ws://localhost:1/ws",
            data_sources_config_url=config_url,
            policy_store=store,
            data_fetcher=fetcher,
            data_topics=["policy_data"],
            should_send_reports=False,
        )
        try:
            # 1st fetch: 200 OK -> writes to policy store
            store.transaction_event.clear()
            async with store.transaction_context(
                "tx-1", transaction_type=TransactionType.data
            ) as tx_1:
                report_1 = await updater._fetch_and_save_data(entry, tx_1)
            assert report_1.fetched is True
            assert report_1.saved is True
            assert len(store.write_calls) == 1
            assert await store.get_data("/roles") == {"roles": {"admin": True}}

            # 2nd fetch: 304 Not Modified -> skips store write, reports fetched=True, saved=False
            async with store.transaction_context(
                "tx-2", transaction_type=TransactionType.data
            ) as tx_2:
                report_2 = await updater._fetch_and_save_data(entry, tx_2)
            assert report_2.fetched is True
            assert report_2.saved is False
            assert len(store.write_calls) == 1
            assert state["requests"][1].get("If-None-Match") == '"etag-100"'

            # Base fetch (simulating reconnect / store re-init) clears cached validators
            await updater.get_base_policy_data(config_url=config_url)
            await updater._tasks.shutdown()
            assert len(store.write_calls) == 2
            assert "If-None-Match" not in state["requests"][2]
        finally:
            await fetcher.stop()
