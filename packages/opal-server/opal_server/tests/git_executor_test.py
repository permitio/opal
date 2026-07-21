import asyncio
import threading
import time

import pytest
from concurrent.futures import thread as cf_thread
from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import (
    _DaemonThreadPoolExecutor,
    git_op_in_flight,
    run_in_git_executor,
)


def test_daemon_worker_not_registered_in_global_join_queue():
    """A worker thread must NOT land in concurrent.futures' _threads_queues.

    The stdlib's _python_exit atexit handler joins every thread in that global
    regardless of daemon=True, so a registered worker running a hung git call
    would block interpreter shutdown — the "stuck on an offline repo" hang this
    executor exists to prevent, relocated to process exit / rolling restart.
    """
    ex = _DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="test-daemon")
    gate = threading.Event()
    try:
        ex.submit(gate.wait)  # forces one worker thread to spawn
        for _ in range(200):
            if ex._threads:
                break
            time.sleep(0.01)
        assert ex._threads, "no worker thread spawned"
        registered = set(ex._threads) & set(cf_thread._threads_queues)
        assert not registered, (
            "daemon worker registered in _threads_queues; _python_exit would "
            "join it and block shutdown on a hung git op"
        )
    finally:
        gate.set()
        ex.shutdown(wait=True)


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


@pytest.mark.asyncio
async def test_zombie_does_not_consume_capacity(monkeypatch):
    """A timed-out (lingering) op must not starve the next op — the bed's
    offline-repo gate: N hung > pool size permanently exhausted the old
    fixed pool. With max workers = 1, a zombie plus a healthy op is the
    minimal starvation scenario."""
    from opal_server.config import opal_server_config
    from opal_server.git_fetcher import shutdown_git_executor

    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 1)
    shutdown_git_executor()  # drop any semaphore minted with the old size
    try:
        release = threading.Event()
        with pytest.raises(TimeoutError):
            await run_in_git_executor(release.wait, timeout=0.1)  # zombie now lingers

        start = time.monotonic()
        result = await asyncio.wait_for(
            run_in_git_executor(lambda: "healthy", timeout=5), timeout=2
        )
        elapsed = time.monotonic() - start
        assert result == "healthy"
        assert elapsed < 1.5, f"healthy op starved behind a zombie ({elapsed:.2f}s)"
    finally:
        release.set()  # let the zombie thread finish
        shutdown_git_executor()


@pytest.mark.asyncio
async def test_cancelled_op_releases_its_semaphore_slot(monkeypatch):
    """Cancelling the awaiting task must still release the live-op semaphore
    slot; otherwise every cancellation permanently shrinks concurrency.

    Uses a nonzero timeout so the cancellation lands inside
    ``await asyncio.wait({fut}, timeout=timeout)`` -- the specific await that
    (pre-fix) was not wrapped in the outer try/finally (the no-timeout
    ``await fut`` branch already had its own per-branch finally, so a
    timeout=0 op would not have exercised the gap this test guards)."""
    from opal_server.config import opal_server_config
    from opal_server.git_fetcher import shutdown_git_executor

    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 1)
    shutdown_git_executor()
    gate = threading.Event()
    try:
        first = asyncio.ensure_future(run_in_git_executor(gate.wait, timeout=5))
        await asyncio.sleep(0.05)  # first holds the only slot, awaiting asyncio.wait
        first.cancel()
        try:
            await first
        except asyncio.CancelledError:
            pass
        # the slot must be free again
        second = await asyncio.wait_for(
            run_in_git_executor(lambda: "ok", timeout=5), timeout=2
        )
        assert second == "ok"
    finally:
        gate.set()
        shutdown_git_executor()


def test_reset_caches_frees_and_clears_all():
    """The gunicorn master must not fork with populated fetcher caches.

    A forked worker that never syncs (sync is leader-only) can only ever
    populate ``repos``/``repos_last_fetched``/``repo_locks`` by inheriting
    them from the master's preload. A client-less non-leader worker's
    broadcaster reader never runs, so it would never receive the purge
    confirmation and would pin an inherited handle for life. This asserts
    the pre-fork reset actually frees the cached handle (not just drops the
    reference) and clears all three caches.
    """
    from opal_server.git_fetcher import GitPolicyFetcher

    freed = []

    class _Handle:
        def free(self):
            freed.append(True)

    try:
        GitPolicyFetcher.repos["/clones/x"] = _Handle()
        GitPolicyFetcher.repos_last_fetched["sid"] = "ts"
        GitPolicyFetcher.repo_locks["sid"] = object()

        GitPolicyFetcher.reset_caches()

        assert not GitPolicyFetcher.repos
        assert not GitPolicyFetcher.repos_last_fetched
        assert not GitPolicyFetcher.repo_locks
        assert freed == [True], "cached pygit2 handle was not free()'d"
    finally:
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.repo_locks.clear()


@pytest.mark.asyncio
async def test_semaphore_bounds_live_ops(monkeypatch):
    """Live ops beyond SCOPES_GIT_MAX_WORKERS queue on the semaphore."""
    from opal_server.config import opal_server_config
    from opal_server.git_fetcher import shutdown_git_executor

    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 1)
    shutdown_git_executor()
    gate = threading.Event()
    try:
        first = asyncio.ensure_future(run_in_git_executor(gate.wait, timeout=0))
        await asyncio.sleep(0.05)  # first op occupies the only live slot
        second = asyncio.ensure_future(run_in_git_executor(lambda: "second", timeout=5))
        await asyncio.sleep(0.05)
        assert not second.done(), "second op ran despite the live-op bound"
        gate.set()
        assert await asyncio.wait_for(second, timeout=2) == "second"
        await asyncio.wait_for(first, timeout=2)
    finally:
        gate.set()
        shutdown_git_executor()
