"""Unit tests for the OpaClient policy-store liveness probe.

These tests cover the four-cell matrix from the spec:

  (a) transactions OK + OPA reachable        -> healthy
  (b) transactions FAILED + OPA reachable    -> unhealthy
  (c) transactions OK + OPA unreachable      -> unhealthy
  (d) recovery from (c): OPA returns         -> healthy

The probe makes a real HTTP call against `POLICY_STORE_URL/health`. We avoid
mocking the OpaClient internals and instead spin up a tiny aiohttp server
to control reachability deterministically.
"""

import asyncio
import contextlib
import socket
import time
from typing import AsyncIterator, Optional, Tuple

import pytest
from aiohttp import web
from opal_client.config import opal_client_config
from opal_client.policy_store.opa_client import OpaClient
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.store import StoreTransaction, TransactionType


def _make_transaction(
    success: bool, transaction_type: TransactionType
) -> StoreTransaction:
    return StoreTransaction(
        id="test-id",
        actions=["set_policy_data"],
        transaction_type=transaction_type,
        success=success,
        error="" if success else "boom",
    )


def _record_successful_transactions(client: OpaClient) -> None:
    """Mark both policy and data transactions as recently successful."""
    client._transaction_state.process_transaction(
        _make_transaction(True, TransactionType.policy)
    )
    client._transaction_state.process_transaction(
        _make_transaction(True, TransactionType.data)
    )


def _record_failed_data_transaction(client: OpaClient) -> None:
    client._transaction_state.process_transaction(
        _make_transaction(True, TransactionType.policy)
    )
    client._transaction_state.process_transaction(
        _make_transaction(False, TransactionType.data)
    )


def _reserve_unused_port() -> int:
    """Reserve a port that's likely free.

    Used only by tests that need a *deliberately unbound* port (e.g. to
    simulate connection-refused). For tests that bind a server, prefer the
    `_ToggleHealthServer` flow which lets aiohttp pick the port and reads
    it back — there is no race window between bind and connect there.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


class _ToggleHealthServer:
    """Tiny aiohttp server that exposes `/health`.

    The handler can be flipped between healthy (200), broken (503) or hanging
    (sleeps long enough to exceed the probe timeout) at runtime.
    """

    HEALTHY = "healthy"
    UNHEALTHY_5XX = "unhealthy_5xx"
    UNHEALTHY_HANG = "unhealthy_hang"

    def __init__(self) -> None:
        self.mode: str = self.HEALTHY
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.port: int = 0

    async def start(self) -> str:
        app = web.Application()
        app.router.add_get("/health", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        # Let aiohttp bind to an ephemeral port; reading the bound port back
        # avoids the bind-then-close-then-rebind race that
        # `_reserve_unused_port` would have.
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        sockets = self._site._server.sockets  # type: ignore[union-attr]
        assert sockets, "aiohttp site started without a bound socket"
        self.port = sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{self.port}"

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        if self.mode == self.HEALTHY:
            return web.Response(status=200, text="ok")
        if self.mode == self.UNHEALTHY_5XX:
            return web.Response(status=503, text="down")
        # UNHEALTHY_HANG: sleep longer than the configured probe timeout
        # so the client side hits its own ClientTimeout.
        await asyncio.sleep(60)
        return web.Response(status=200, text="ok")


@contextlib.asynccontextmanager
async def _toggle_server() -> AsyncIterator[Tuple[_ToggleHealthServer, str]]:
    server = _ToggleHealthServer()
    base_url = await server.start()
    try:
        yield server, base_url
    finally:
        await server.stop()


@contextlib.asynccontextmanager
async def _override_config(**overrides):
    saved = {key: getattr(opal_client_config, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(opal_client_config, key, value)
        yield
    finally:
        for key, value in saved.items():
            setattr(opal_client_config, key, value)


async def _wait_for_engine_reachable(
    client: OpaClient, expected: bool, timeout: float = 5.0
) -> None:
    """Poll until the transaction state's `engine_reachable` matches `expected`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client._transaction_state.engine_reachable is expected:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"engine_reachable did not become {expected} within {timeout}s "
        f"(actual={client._transaction_state.engine_reachable})"
    )


def _make_client(
    opa_base_url: str,
    *,
    auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
    oauth_client_id: Optional[str] = None,
    oauth_client_secret: Optional[str] = None,
    oauth_server: Optional[str] = None,
) -> OpaClient:
    return OpaClient(
        opa_server_url=opa_base_url,
        opa_auth_token=None,
        auth_type=auth_type,
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
        oauth_server=oauth_server,
        data_updater_enabled=True,
        policy_updater_enabled=True,
        cache_policy_data=False,
        tls_client_cert=None,
        tls_client_key=None,
        tls_ca=None,
    )


@pytest.mark.asyncio
async def test_healthy_when_transactions_ok_and_engine_reachable():
    """Matrix cell (a): transactions OK + OPA reachable -> healthy."""
    async with _toggle_server() as (_server, base_url):
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = _make_client(base_url)
            _record_successful_transactions(client)
            try:
                await client.start_liveness_probe()
                # The first probe runs synchronously inside
                # `start_liveness_probe`, so reachability is already true here.
                assert client._transaction_state.engine_reachable is True
                assert await client.is_healthy() is True
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_unhealthy_when_transactions_failed_even_if_engine_reachable():
    """Matrix cell (b): transactions FAILED + OPA reachable -> unhealthy."""
    async with _toggle_server() as (_server, base_url):
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = _make_client(base_url)
            _record_failed_data_transaction(client)
            try:
                await client.start_liveness_probe()
                await _wait_for_engine_reachable(client, True)
                assert await client.is_healthy() is False
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_unhealthy_when_transactions_ok_but_engine_unreachable_5xx():
    """Matrix cell (c): transactions OK + OPA returns 5xx -> unhealthy.

    This simulates an OPA that is process-up but answering errors on /health.
    """
    async with _toggle_server() as (server, base_url):
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = _make_client(base_url)
            _record_successful_transactions(client)
            server.mode = _ToggleHealthServer.UNHEALTHY_5XX
            try:
                await client.start_liveness_probe()
                await _wait_for_engine_reachable(client, False)
                assert await client.is_healthy() is False
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_unhealthy_when_engine_hangs_then_recovers():
    """Matrix cell (c) with hang + cell (d) recovery.

    The probe must trip to unhealthy when OPA stops responding within the
    configured timeout, then automatically recover when OPA returns.
    """
    async with _toggle_server() as (server, base_url):
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = _make_client(base_url)
            _record_successful_transactions(client)
            try:
                await client.start_liveness_probe()
                # Initially healthy.
                await _wait_for_engine_reachable(client, True)
                assert await client.is_healthy() is True

                # Simulate OPA hang.
                server.mode = _ToggleHealthServer.UNHEALTHY_HANG
                await _wait_for_engine_reachable(client, False, timeout=10.0)
                assert await client.is_healthy() is False

                # OPA recovers.
                server.mode = _ToggleHealthServer.HEALTHY
                await _wait_for_engine_reachable(client, True, timeout=10.0)
                assert await client.is_healthy() is True
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_unhealthy_when_engine_url_unreachable_connection_refused():
    """OPA process gone (connection refused) -> probe trips to unhealthy."""
    free_port = _reserve_unused_port()
    async with _override_config(
        POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
        POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
        POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
    ):
        client = _make_client(f"http://127.0.0.1:{free_port}")
        _record_successful_transactions(client)
        try:
            await client.start_liveness_probe()
            await _wait_for_engine_reachable(client, False, timeout=5.0)
            assert await client.is_healthy() is False
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_probe_disabled_keeps_engine_reachable_true():
    """With the probe disabled, /healthy is driven only by the transaction
    state — engine_reachable is never flipped."""
    async with _override_config(POLICY_STORE_LIVENESS_PROBE_ENABLED=False):
        client = _make_client("http://127.0.0.1:1")  # unreachable on purpose
        _record_successful_transactions(client)
        await client.start_liveness_probe()
        # No task should have been started.
        assert client._liveness_probe_task is None
        # And /healthy should still report healthy because the transaction
        # state is healthy and the probe didn't flip the flag.
        assert await client.is_healthy() is True
        await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_stop_is_idempotent_and_does_not_raise():
    async with _override_config(
        POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
        POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
        POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
    ):
        client = _make_client("http://127.0.0.1:1")
        await client.start_liveness_probe()
        # Stopping multiple times is safe.
        await client.stop_liveness_probe()
        await client.stop_liveness_probe()
        assert client._liveness_probe_task is None


@pytest.mark.asyncio
async def test_start_is_idempotent_and_reuses_same_task():
    """A second `start_liveness_probe` while one is running must be a no-op."""
    async with _toggle_server() as (_server, base_url):
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = _make_client(base_url)
            try:
                await client.start_liveness_probe()
                first_task = client._liveness_probe_task
                first_session = client._liveness_probe_session
                assert first_task is not None
                assert first_session is not None

                # Second call must not spawn a second task or session.
                await client.start_liveness_probe()
                assert client._liveness_probe_task is first_task
                assert client._liveness_probe_session is first_session
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_probe_ignores_oauth_failures():
    """The probe must not couple to the OAuth token-fetch path.

    With OAuth configured against an unreachable IdP, the probe should still
    report OPA as reachable when OPA itself is up, because OPA's `/health`
    is unauthenticated by default and the probe sends no auth headers.
    """
    async with _toggle_server() as (_server, base_url):
        # Point OAuth at an obviously-broken host. If the probe were calling
        # `_get_auth_headers()` the token fetch would hang or fail and the
        # probe would (incorrectly) report unreachable.
        unreachable_oauth_port = _reserve_unused_port()
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = _make_client(
                base_url,
                auth_type=PolicyStoreAuth.OAUTH,
                oauth_client_id="id",
                oauth_client_secret="secret",
                oauth_server=f"http://127.0.0.1:{unreachable_oauth_port}/oauth",
            )
            _record_successful_transactions(client)
            try:
                await client.start_liveness_probe()
                await _wait_for_engine_reachable(client, True, timeout=5.0)
                assert await client.is_healthy() is True
            finally:
                await client.stop_liveness_probe()
