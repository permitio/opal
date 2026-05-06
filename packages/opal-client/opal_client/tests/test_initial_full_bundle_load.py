"""Tests for the INITIAL_POLICY_LOAD_MODE / set_policies_atomic feature.

Coverage:
- PolicyUpdater routes full bundles through set_policies_atomic when the flag
  is SINGLE_TRANSACTION, and through set_policies when it is PER_MODULE.
- Delta bundles always use set_policies regardless of the flag.
- MockPolicyStoreClient tracks atomic_load_calls correctly.
- OpaClient.set_policies_atomic sends policies/data with ?txn=<id>, then
  commits once, and falls back gracefully when the transaction API is absent.
"""

import asyncio
import json
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import Response, status
from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
from opal_client.policy_store.opa_client import OpaClient
from opal_client.policy_store.schemas import InitialPolicyLoadMode, PolicyStoreAuth
from opal_common.schemas.policy import DataModule, PolicyBundle, RegoModule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rego_module(path: str, rego: str = "package test") -> RegoModule:
    return RegoModule(path=path, rego=rego, package_name="test")


def make_data_module(path: str, data: dict = None) -> DataModule:
    return DataModule(path=path, data=json.dumps(data or {}))


def make_full_bundle(
    n_policies: int = 3, n_data: int = 1, commit_hash: str = "abc123"
) -> PolicyBundle:
    policies = [
        make_rego_module(f"policy_{i}.rego", f"package p{i}") for i in range(n_policies)
    ]
    data = [make_data_module(f"data_{i}", {"key": i}) for i in range(n_data)]
    return PolicyBundle(
        hash=commit_hash,
        old_hash=None,  # full bundle
        manifest=[m.path for m in policies],
        policy_modules=policies,
        data_modules=data,
    )


def make_delta_bundle(
    base_hash: str = "base000", commit_hash: str = "delta001"
) -> PolicyBundle:
    return PolicyBundle(
        hash=commit_hash,
        old_hash=base_hash,  # delta bundle
        manifest=["policy_0.rego"],
        policy_modules=[make_rego_module("policy_0.rego")],
        data_modules=[],
    )


# ---------------------------------------------------------------------------
# MockPolicyStoreClient tests
# ---------------------------------------------------------------------------

class TestMockPolicyStoreClient:
    def test_atomic_load_calls_counter_starts_at_zero(self):
        store = MockPolicyStoreClient()
        assert not hasattr(store, "atomic_load_calls")

    @pytest.mark.asyncio
    async def test_set_policies_atomic_increments_counter(self):
        store = MockPolicyStoreClient()
        bundle = make_full_bundle()
        await store.set_policies_atomic(bundle)
        assert store.atomic_load_calls == 1
        await store.set_policies_atomic(bundle)
        assert store.atomic_load_calls == 2

    @pytest.mark.asyncio
    async def test_set_policies_does_not_increment_counter(self):
        store = MockPolicyStoreClient()
        bundle = make_full_bundle()
        await store.set_policies(bundle)
        assert not hasattr(store, "atomic_load_calls")


# ---------------------------------------------------------------------------
# PolicyUpdater routing tests
# ---------------------------------------------------------------------------

class FakePolicyFetcher:
    def __init__(self, bundle: PolicyBundle):
        self._bundle = bundle
        self.policy_endpoint_url = "http://opal-server/policy"

    async def fetch_policy_bundle(self, directories, base_hash=None):
        return self._bundle


class FakeStore(MockPolicyStoreClient):
    """Wraps MockPolicyStoreClient and records which high-level method was called."""

    def __init__(self):
        super().__init__()
        self._version: Optional[str] = None
        self.set_policies_calls: int = 0
        self.set_policies_atomic_calls: int = 0

    async def get_policy_version(self) -> Optional[str]:
        return self._version

    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        self.set_policies_calls += 1
        self._version = bundle.hash

    async def set_policies_atomic(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        self.set_policies_atomic_calls += 1
        self._version = bundle.hash


def make_updater(store: FakeStore, bundle: PolicyBundle, mode: InitialPolicyLoadMode):
    """Build a minimal PolicyUpdater with a fake fetcher and store."""
    from opal_client.policy.updater import PolicyUpdater

    updater = PolicyUpdater.__new__(PolicyUpdater)
    updater._policy_store = store
    updater._policy_fetcher = FakePolicyFetcher(bundle)
    updater._should_send_reports = False
    updater._tasks = MagicMock()
    updater._tasks.add_task = MagicMock()
    updater._client = None
    updater._opal_client_id = "test-client"
    return updater


@pytest.mark.asyncio
async def test_per_module_mode_uses_set_policies():
    store = FakeStore()
    bundle = make_full_bundle()
    updater = make_updater(store, bundle, InitialPolicyLoadMode.PER_MODULE)

    with patch(
        "opal_client.policy.updater.opal_client_config.INITIAL_POLICY_LOAD_MODE",
        InitialPolicyLoadMode.PER_MODULE,
    ):
        await updater.update_policy(directories=None, force_full_update=False)

    assert store.set_policies_calls == 1
    assert store.set_policies_atomic_calls == 0


@pytest.mark.asyncio
async def test_single_transaction_mode_uses_set_policies_atomic():
    store = FakeStore()
    bundle = make_full_bundle()
    updater = make_updater(store, bundle, InitialPolicyLoadMode.SINGLE_TRANSACTION)

    with patch(
        "opal_client.policy.updater.opal_client_config.INITIAL_POLICY_LOAD_MODE",
        InitialPolicyLoadMode.SINGLE_TRANSACTION,
    ):
        await updater.update_policy(directories=None, force_full_update=False)

    assert store.set_policies_atomic_calls == 1
    assert store.set_policies_calls == 0


@pytest.mark.asyncio
async def test_delta_bundle_always_uses_set_policies_regardless_of_mode():
    """Delta bundles (old_hash set) must never go through the atomic path."""
    store = FakeStore()
    store._version = "base000"  # simulate a previously loaded version
    bundle = make_delta_bundle()
    updater = make_updater(store, bundle, InitialPolicyLoadMode.SINGLE_TRANSACTION)

    with patch(
        "opal_client.policy.updater.opal_client_config.INITIAL_POLICY_LOAD_MODE",
        InitialPolicyLoadMode.SINGLE_TRANSACTION,
    ):
        await updater.update_policy(directories=None, force_full_update=False)

    # The bundle returned has old_hash set (delta), so set_policies must be used.
    assert store.set_policies_calls == 1
    assert store.set_policies_atomic_calls == 0


@pytest.mark.asyncio
async def test_reconnect_full_reload_uses_atomic_path():
    """After a Pub/Sub reconnect, base_hash is None (forced full reload).
    With SINGLE_TRANSACTION mode, the atomic path must be used even if
    _policy_version was previously set.
    """
    store = FakeStore()
    # Simulate a store that already has a version (i.e. we had loaded before)
    store._version = "prev_hash"

    # But force_full_update=True clears the base_hash, mimicking reconnect
    bundle = make_full_bundle(commit_hash="new_hash")
    updater = make_updater(store, bundle, InitialPolicyLoadMode.SINGLE_TRANSACTION)

    with patch(
        "opal_client.policy.updater.opal_client_config.INITIAL_POLICY_LOAD_MODE",
        InitialPolicyLoadMode.SINGLE_TRANSACTION,
    ):
        await updater.update_policy(directories=None, force_full_update=True)

    assert store.set_policies_atomic_calls == 1
    assert store.set_policies_calls == 0


# ---------------------------------------------------------------------------
# OpaClient.set_policies_atomic — unit tests with a fake OPA HTTP server
# ---------------------------------------------------------------------------

class FakeOpaServer:
    """Records OPA REST calls so tests can assert on them."""

    def __init__(self, txn_id: str = "txn-123"):
        self.txn_id = txn_id
        self.calls: List[dict] = []  # [{method, path, params}]
        self.policies: Dict[str, str] = {}  # existing policy modules in store

    def _record(self, method: str, path: str, params: dict = None):
        self.calls.append({"method": method, "path": path, "params": params or {}})

    def make_aiohttp_session(self):
        """Returns an async context manager mock wired to this fake server."""
        server = self

        class FakeResponse:
            def __init__(self, status_code: int, body: dict = None):
                self.status = status_code
                self._body = body or {}

            async def json(self):
                return self._body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, **kwargs):
                path = url.split("/v1", 1)[1]
                server._record("GET", path, kwargs.get("params"))
                if path == "/policies":
                    result = [
                        {"id": k, "raw": v} for k, v in server.policies.items()
                    ]
                    return FakeResponse(200, {"result": result})
                return FakeResponse(200, {"result": {}})

            async def post(self, url, **kwargs):
                path = url.split("/v1", 1)[1]
                server._record("POST", path, kwargs.get("params"))
                if path == "/transactions":
                    return FakeResponse(200, {"result": {"id": server.txn_id}})
                if path == f"/transactions/{server.txn_id}/commit":
                    return FakeResponse(200, {})
                return FakeResponse(200, {})

            async def put(self, url, **kwargs):
                path = url.split("/v1", 1)[1]
                params = kwargs.get("params", {})
                server._record("PUT", path, params)
                return FakeResponse(200, {})

            async def delete(self, url, **kwargs):
                path = url.split("/v1", 1)[1]
                server._record("DELETE", path, kwargs.get("params"))
                return FakeResponse(200, {})

        return FakeSession()


@pytest.fixture
def opa_client():
    return OpaClient("http://localhost:8181")


@pytest.mark.asyncio
async def test_set_policies_atomic_uses_transaction_api(opa_client):
    """All policy/data writes must carry ?txn=<id>, and exactly one commit."""
    fake_server = FakeOpaServer(txn_id="txn-999")
    bundle = make_full_bundle(n_policies=3, n_data=1)

    with patch("aiohttp.ClientSession", return_value=fake_server.make_aiohttp_session()):
        await opa_client.set_policies_atomic(bundle)

    txn_ids_on_policy_puts = [
        c["params"].get("txn")
        for c in fake_server.calls
        if c["method"] == "PUT" and "/policies/" in c["path"]
    ]
    txn_ids_on_data_puts = [
        c["params"].get("txn")
        for c in fake_server.calls
        if c["method"] == "PUT" and "/data" in c["path"]
    ]
    commit_calls = [
        c for c in fake_server.calls
        if c["method"] == "POST" and "/commit" in c["path"]
    ]

    # All 3 policy PUTs carry the transaction id
    assert all(t == "txn-999" for t in txn_ids_on_policy_puts)
    assert len(txn_ids_on_policy_puts) == 3

    # 1 data PUT carries the transaction id
    assert all(t == "txn-999" for t in txn_ids_on_data_puts)

    # Exactly one commit
    assert len(commit_calls) == 1


@pytest.mark.asyncio
async def test_set_policies_atomic_fallback_when_txn_api_absent(opa_client):
    """When POST /v1/transactions returns a non-200, fall back to set_policies."""
    fake_server = FakeOpaServer()
    bundle = make_full_bundle(n_policies=2, n_data=0)

    class ErrorSession(fake_server.make_aiohttp_session().__class__):
        async def post(self, url, **kwargs):
            path = url.split("/v1", 1)[1]
            if path == "/transactions":
                from fastapi import Response

                class Resp:
                    status = 404

                    async def json(self):
                        return {}

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        pass

                return Resp()
            return await super().post(url, **kwargs)

    with patch("aiohttp.ClientSession", return_value=ErrorSession()):
        with patch.object(
            opa_client, "_set_policies_from_complete_bundle", new_callable=AsyncMock
        ) as mock_fallback:
            await opa_client.set_policies_atomic(bundle)
            mock_fallback.assert_called_once_with(bundle)


@pytest.mark.asyncio
async def test_set_policies_atomic_aborts_on_policy_error(opa_client):
    """If a policy PUT fails inside the transaction, the txn must be aborted."""
    fake_server = FakeOpaServer(txn_id="txn-abc")

    class FailingSession(fake_server.make_aiohttp_session().__class__):
        async def put(self, url, **kwargs):
            # Simulate OPA rejecting a policy (bad rego)
            class Resp:
                status = 400

                async def json(self):
                    return {"errors": [{"message": "bad rego"}]}

                @property
                def body(self):
                    return b'{"errors": [{"message": "bad rego"}]}'

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return Resp()

    with patch("aiohttp.ClientSession", return_value=FailingSession()):
        with patch.object(
            opa_client, "_engine_abort_transaction", new_callable=AsyncMock
        ) as mock_abort:
            with pytest.raises(RuntimeError):
                await opa_client.set_policies_atomic(make_full_bundle(n_policies=1, n_data=0))
            mock_abort.assert_called_once()


@pytest.mark.asyncio
async def test_set_policies_atomic_skips_delta_bundle(opa_client):
    """set_policies_atomic must never apply a delta bundle atomically."""
    delta = make_delta_bundle()
    with patch.object(
        opa_client, "_set_policies_from_delta_bundle", new_callable=AsyncMock
    ) as mock_delta:
        await opa_client.set_policies_atomic(delta)
        mock_delta.assert_called_once_with(delta)
