"""Unit tests for the CedarClient policy-store liveness probe.

CedarClient inherits the same `LivenessProbeMixin` as `OpaClient`, so most
of the lifecycle behavior is exercised in the OPA suite. This file covers
the Cedar-specific surface: that the probe reaches the cedar-agent's
`/v1/` endpoint (matching `CedarRunner.health_check()`'s precedent) and
that the result feeds into `is_healthy()`.
"""

import asyncio
import contextlib
import time
from typing import AsyncIterator, Optional, Tuple

import pytest
from aiohttp import web
from opal_client.config import opal_client_config
from opal_client.policy_store.cedar_client import CedarClient
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


def _record_successful_transactions(client: CedarClient) -> None:
    client._most_recent_policy_transaction = _make_transaction(
        True, TransactionType.policy
    )
    client._most_recent_data_transaction = _make_transaction(
        True, TransactionType.data
    )


class _ToggleCedarServer:
    """Tiny aiohttp server that exposes `/v1/` (matching cedar-agent)."""

    HEALTHY = "healthy"
    UNHEALTHY_5XX = "unhealthy_5xx"

    def __init__(self) -> None:
        self.mode: str = self.HEALTHY
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.port: int = 0

    async def start(self) -> str:
        app = web.Application()
        # cedar-agent serves 2xx on `/v1/`; mirror that.
        app.router.add_get("/v1/", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
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
        return web.Response(status=503, text="down")


@contextlib.asynccontextmanager
async def _toggle_server() -> AsyncIterator[Tuple[_ToggleCedarServer, str]]:
    server = _ToggleCedarServer()
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
    client: CedarClient, expected: bool, timeout: float = 5.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client._engine_reachable is expected:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"engine_reachable did not become {expected} within {timeout}s "
        f"(actual={client._engine_reachable})"
    )


def _make_client(base_url: str) -> CedarClient:
    return CedarClient(
        cedar_server_url=base_url,
        cedar_auth_token=None,
        auth_type=PolicyStoreAuth.NONE,
    )


@pytest.mark.asyncio
async def test_healthy_when_transactions_ok_and_cedar_reachable():
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
                # First probe runs synchronously inside start_liveness_probe.
                assert client._engine_reachable is True
                assert await client.is_healthy() is True
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_unhealthy_when_cedar_returns_5xx():
    async with _toggle_server() as (server, base_url):
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = _make_client(base_url)
            _record_successful_transactions(client)
            server.mode = _ToggleCedarServer.UNHEALTHY_5XX
            try:
                await client.start_liveness_probe()
                await _wait_for_engine_reachable(client, False, timeout=5.0)
                assert await client.is_healthy() is False
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_recovery_after_cedar_returns():
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
                await _wait_for_engine_reachable(client, True)
                assert await client.is_healthy() is True

                server.mode = _ToggleCedarServer.UNHEALTHY_5XX
                await _wait_for_engine_reachable(client, False, timeout=10.0)
                assert await client.is_healthy() is False

                server.mode = _ToggleCedarServer.HEALTHY
                await _wait_for_engine_reachable(client, True, timeout=10.0)
                assert await client.is_healthy() is True
            finally:
                await client.stop_liveness_probe()
