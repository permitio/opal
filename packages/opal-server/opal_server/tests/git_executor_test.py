import asyncio
import threading
import time

import pytest
from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import git_op_in_flight, run_in_git_executor


def test_git_resilience_config_defaults(monkeypatch):
    # Don't let an ambient OPAL_* env var in CI/dev shadow the declared defaults.
    monkeypatch.delenv("OPAL_SCOPES_GIT_FETCH_TIMEOUT", raising=False)
    monkeypatch.delenv("OPAL_SCOPES_GIT_MAX_WORKERS", raising=False)
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_GIT_FETCH_TIMEOUT == 120.0
    assert clean.SCOPES_GIT_MAX_WORKERS == 10


@pytest.mark.asyncio
async def test_run_in_git_executor_returns_value():
    result = await run_in_git_executor(lambda: 21 * 2, timeout=5)
    assert result == 42


@pytest.mark.asyncio
async def test_run_in_git_executor_times_out():
    with pytest.raises(TimeoutError):
        await run_in_git_executor(lambda: time.sleep(1), timeout=0.1)


@pytest.mark.asyncio
async def test_zero_timeout_means_no_limit():
    result = await run_in_git_executor(lambda: "ok", timeout=0)
    assert result == "ok"


def test_git_op_in_flight_false_for_unknown_key():
    assert git_op_in_flight("no-such-source") is False


@pytest.mark.asyncio
async def test_busy_key_stays_in_flight_until_call_returns():
    """A timed-out op must remain 'in flight' until its blocking call actually
    returns, so a second op for the same repo is not started concurrently."""
    started = threading.Event()
    release = threading.Event()
    key = "busy-source-id"

    def _block():
        started.set()
        release.wait(5)

    # The op exceeds its timeout but keeps running on the pool thread.
    with pytest.raises(TimeoutError):
        await run_in_git_executor(_block, timeout=0.1, busy_key=key)

    assert started.wait(2)
    # Still lingering on the pool thread -> guarded as in-flight.
    assert git_op_in_flight(key) is True

    # Once the blocking call returns, the marker clears (from the pool thread).
    release.set()
    for _ in range(200):
        if not git_op_in_flight(key):
            break
        await asyncio.sleep(0.01)
    assert git_op_in_flight(key) is False


@pytest.mark.asyncio
async def test_busy_key_cleared_after_success():
    key = "ok-source-id"
    assert await run_in_git_executor(lambda: 1, timeout=5, busy_key=key) == 1
    assert git_op_in_flight(key) is False
