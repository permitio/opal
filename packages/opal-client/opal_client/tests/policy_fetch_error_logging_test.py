"""Policy bundle fetch failures are logged - and recorded in the policy
transaction - without the client token or the bundle contents."""

import json
from typing import List

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from opal_client.config import opal_client_config
from opal_client.policy.fetcher import PolicyFetcher, force_valid_bundle
from opal_client.policy.options import ConnRetryOptions
from opal_client.policy.updater import PolicyUpdater
from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
from opal_common.schemas.store import StoreTransaction
from opal_common.tests.redaction_fixtures import capture_logs
from pydantic import ValidationError

CLIENT_TOKEN = "fake-client-token"
FAKE_KEY = "FAKE-KEY-123"
# rego is required on every policy module; the data module content is the
# sensitive part a log line must not render
INVALID_BUNDLE = {
    "manifest": [],
    "hash": "abc123",
    "data_modules": [{"path": "/", "data": json.dumps({"api_key": FAKE_KEY})}],
    "policy_modules": [{"path": "p.rego", "package_name": "p"}],
}


@pytest.fixture(autouse=True)
def single_attempt(monkeypatch):
    monkeypatch.setattr(
        opal_client_config,
        "POLICY_UPDATER_CONN_RETRY",
        ConnRetryOptions(attempts=1, wait_time=0),
    )


async def _invalid_bundle(request: web.Request) -> web.Response:
    return web.json_response(INVALID_BUNDLE)


async def _redirect_loop(request: web.Request) -> web.Response:
    raise web.HTTPFound("/policy")


async def _html_bad_gateway(request: web.Request) -> web.Response:
    return web.Response(
        status=502, text="<html>502 Bad Gateway</html>", content_type="text/html"
    )


def _server(handler) -> TestServer:
    app = web.Application()
    app.router.add_get("/policy", handler)
    return TestServer(app)


def _fetcher(server: TestServer) -> PolicyFetcher:
    return PolicyFetcher(
        backend_url=str(server.make_url("")).rstrip("/"), token=CLIENT_TOKEN
    )


def test_invalid_bundle_log_omits_bundle_contents():
    with capture_logs() as logs:
        with pytest.raises(ValidationError) as exc_info:
            force_valid_bundle(INVALID_BUNDLE)

    assert FAKE_KEY not in logs.combined
    assert FAKE_KEY not in str(exc_info.value)
    assert (
        "server returned invalid bundle: 1 validation error for PolicyBundle: "
        "policy_modules.0.rego (missing)"
    ) in logs.text[0]


@pytest.mark.asyncio
async def test_invalid_bundle_fetch_logs_omit_bundle_contents():
    async with _server(_invalid_bundle) as server:
        with capture_logs() as logs:
            with pytest.raises(ValidationError):
                await _fetcher(server).fetch_policy_bundle()

    assert "Failed all attempts to fetch bundle" in logs.combined
    assert FAKE_KEY not in logs.combined
    assert CLIENT_TOKEN not in logs.combined


@pytest.mark.asyncio
async def test_connection_error_logs_omit_client_token():
    """A redirect loop fails with TooManyRedirects carrying the first request,
    whose repr renders the client's Authorization header."""
    async with _server(_redirect_loop) as server:
        with capture_logs() as logs:
            with pytest.raises(Exception) as exc_info:
                await _fetcher(server).fetch_policy_bundle()

    assert CLIENT_TOKEN in repr(exc_info.value)  # what the log lines must not render
    assert "server connection error: TooManyRedirects" in logs.combined
    assert "Failed all attempts to fetch bundle, got error: TooManyRedirects" in (
        logs.combined
    )
    assert CLIENT_TOKEN not in logs.combined


@pytest.mark.asyncio
async def test_html_error_page_fails_with_bad_status_error():
    async with _server(_html_bad_gateway) as server:
        with capture_logs() as logs:
            with pytest.raises(ValueError, match="unexpected response code"):
                await _fetcher(server).fetch_policy_bundle()

    assert "Unexpected response code 502" in logs.combined
    assert CLIENT_TOKEN not in logs.combined


class _RecordingStore(MockPolicyStoreClient):
    def __init__(self):
        super().__init__()
        self.transactions: List[StoreTransaction] = []

    async def log_transaction(self, transaction: StoreTransaction):
        self.transactions.append(transaction)


@pytest.mark.asyncio
async def test_failed_update_records_error_without_client_token(monkeypatch):
    """The fetch error lands in the policy transaction (persisted into OPA's
    health-check policy) and in its ERROR log line."""
    store = _RecordingStore()
    async with _server(_redirect_loop) as server:
        monkeypatch.setattr(
            opal_client_config, "SERVER_URL", str(server.make_url("")).rstrip("/")
        )
        monkeypatch.setattr(opal_client_config, "CLIENT_TOKEN", CLIENT_TOKEN)
        updater = PolicyUpdater(
            token=CLIENT_TOKEN, pubsub_url="ws://localhost:1/ws", policy_store=store
        )
        with capture_logs() as logs:
            await updater.update_policy(directories=["."], force_full_update=True)

    (transaction,) = store.transactions
    assert not transaction.success
    assert transaction.error.startswith("TooManyRedirects: ")
    assert CLIENT_TOKEN not in transaction.model_dump_json()
    assert "OPA transaction failed" in logs.combined
    assert CLIENT_TOKEN not in logs.combined
