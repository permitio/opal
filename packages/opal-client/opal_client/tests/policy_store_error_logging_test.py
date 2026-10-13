"""Policy store (OPA / Cedar) connection errors are logged without the auth
header the client sent: aiohttp's ``repr()`` of a response error renders the
request headers."""

import asyncio
import base64

import aiohttp
import pytest
from opal_client.policy_store.cedar_client import CedarClient
from opal_client.policy_store.opa_client import OpaClient
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.policy import DataModule
from opal_common.schemas.store import StoreTransaction, TransactionType
from opal_common.tests.redaction_fixtures import capture_logs, response_error
from pydantic import BaseModel
from tenacity import RetryError

FAKE_KEY = "FAKE-KEY-123"
STORE_URL = "http://policy-store.example.com:8181"


class _FailingRequest:
    def __init__(self, error: Exception):
        self._error = error

    async def __aenter__(self):
        raise self._error

    async def __aexit__(self, *exc_info):
        return False


class _FailingSession:
    """Stands in for ``aiohttp.ClientSession``: every request fails with the
    response error aiohttp would raise, carrying the headers that were sent."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def _request(self, url, headers=None, auth=None, **kwargs):
        sent = dict(headers or {})
        if auth is not None:
            sent["Authorization"] = auth.encode()
        return _FailingRequest(response_error(sent, url=url))

    get = put = post = patch = delete = _request


@pytest.fixture(autouse=True)
def failing_store(monkeypatch):
    monkeypatch.setattr(aiohttp, "ClientSession", _FailingSession)
    # the clients retry with a module-level config fixed at import; skip its waits
    real_sleep = asyncio.sleep

    async def no_wait(delay, *args, **kwargs):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", no_wait)


class _Input(BaseModel):
    user: str = "u"


def _opa(**kwargs) -> OpaClient:
    return OpaClient(STORE_URL, **kwargs)


def _opa_with_token() -> OpaClient:
    return _opa(opa_auth_token=FAKE_KEY, auth_type=PolicyStoreAuth.TOKEN)


OPA_CALLS = {
    "set_policy": lambda c: c.set_policy(policy_id="p", policy_code="package p"),
    "get_policy": lambda c: c.get_policy("p"),
    "get_policies": lambda c: c.get_policies(),
    "delete_policy": lambda c: c.delete_policy("p"),
    "set_policy_data": lambda c: c.set_policy_data({"a": 1}, path="/a"),
    "patch_policy_data": lambda c: c.patch_policy_data([], path="/a"),
    "delete_policy_data": lambda c: c.delete_policy_data(path="/a"),
    "get_data": lambda c: c.get_data("/a"),
    "get_data_with_input": lambda c: c.get_data_with_input("a", _Input()),
    "set_policies-data-module": lambda c: c._set_policy_data_from_bundle_data_module(
        DataModule(path="a", data="{}")
    ),
}


async def _call(call) -> None:
    try:
        await call
    except RetryError:
        pass  # the calls retry, then raise; only the log lines are under test


@pytest.mark.asyncio
@pytest.mark.parametrize("name", OPA_CALLS)
async def test_opa_connection_error_log_omits_auth_header(name):
    client = _opa_with_token()
    with capture_logs() as logs:
        await _call(OPA_CALLS[name](client))

    assert "Opa connection error: ClientResponseError: 502" in logs.combined
    assert FAKE_KEY not in logs.combined


# aiohttp 3.14 deprecates BasicAuth, which OpaClient still uses for OAuth
@pytest.mark.filterwarnings("ignore:BasicAuth is deprecated:DeprecationWarning")
@pytest.mark.asyncio
async def test_opa_oauth_error_log_omits_client_credentials():
    client = _opa(
        auth_type=PolicyStoreAuth.OAUTH,
        oauth_client_id="fake-client",
        oauth_client_secret=FAKE_KEY,
        oauth_server="http://oauth.example.com/token",
    )
    basic_credential = base64.b64encode(f"fake-client:{FAKE_KEY}".encode()).decode()
    with capture_logs() as logs:
        await _call(client.get_policies())

    assert "OAuth server connection error: ClientResponseError" in logs.combined
    assert FAKE_KEY not in logs.combined
    assert basic_credential not in logs.combined


@pytest.mark.asyncio
async def test_opa_non_json_data_module_log_omits_module_contents():
    client = _opa_with_token()
    module = DataModule(path="a", data='{"api_key": "' + FAKE_KEY)
    with capture_logs() as logs:
        await client._set_policy_data_from_bundle_data_module(module)

    assert "bundle contains non-json data module: /a" in logs.combined
    assert "JSONDecodeError: Unterminated string" in logs.combined
    assert FAKE_KEY not in logs.combined


@pytest.mark.asyncio
async def test_opa_transaction_log_write_error_omits_auth_header():
    client = _opa_with_token()
    await _call(client.init_healthcheck_policy("opal/healthcheck", "package h"))
    transaction = StoreTransaction(
        id="t1", actions=["set_policy"], transaction_type=TransactionType.policy
    )
    with capture_logs() as logs:
        await client.log_transaction(transaction)

    assert "Cannot write to OPAL transaction log" in logs.combined
    assert FAKE_KEY not in logs.combined


@pytest.mark.asyncio
async def test_failed_transaction_error_omits_auth_header():
    """An error raised inside a store transaction becomes the transaction's
    ``error``, which is logged and persisted into OPA's health-check policy."""
    client = _opa_with_token()
    error = response_error({"Authorization": f"Bearer {FAKE_KEY}"})
    with capture_logs() as logs:
        with pytest.raises(aiohttp.ClientResponseError):
            async with client.transaction_context(
                "t1", transaction_type=TransactionType.policy
            ) as store_transaction:
                # a transaction with no recorded action is not logged at all
                await _call(store_transaction.set_policy("p", "package p"))
                raise error

    assert (
        "OPA transaction failed, transaction id=t1, actions=['set_policy'], "
        "error=ClientResponseError: 502"
    ) in logs.combined
    # the transaction as recorded, logged at DEBUG when it is processed
    assert "processing store transaction" in logs.combined
    assert FAKE_KEY not in logs.combined


CEDAR_CALLS = {
    "set_policy": lambda c: c.set_policy(policy_id="p", policy_code="permit;"),
    "get_policy": lambda c: c.get_policy("p"),
    "get_policies": lambda c: c.get_policies(),
    "delete_policy": lambda c: c.delete_policy("p"),
    "set_policy_data": lambda c: c.set_policy_data([]),
    "delete_policy_data": lambda c: c.delete_policy_data(),
    "get_data": lambda c: c.get_data(""),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CEDAR_CALLS)
async def test_cedar_connection_error_log_omits_auth_header(name):
    client = CedarClient(
        STORE_URL, cedar_auth_token=FAKE_KEY, auth_type=PolicyStoreAuth.TOKEN
    )
    with capture_logs() as logs:
        await _call(CEDAR_CALLS[name](client))

    assert "Cedar Agent connection error: ClientResponseError: 502" in logs.combined
    assert FAKE_KEY not in logs.combined
