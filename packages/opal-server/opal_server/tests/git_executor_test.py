import asyncio
import pathlib
import threading
import time
from concurrent.futures import thread as cf_thread

import pytest
from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import (
    _DaemonThreadPoolExecutor,
    git_op_in_flight,
    run_in_git_executor,
)


def test_daemon_worker_not_registered_in_global_join_queue():
    """A worker thread must NOT land in concurrent.futures' _threads_queues.

    The stdlib's _python_exit atexit handler joins every thread in that
    global regardless of daemon=True, so a registered worker running a
    hung git call would block interpreter shutdown — the "stuck on an
    offline repo" hang this executor exists to prevent, relocated to
    process exit / rolling restart.
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
    monkeypatch.delenv("OPAL_SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT", raising=False)
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_GIT_FETCH_TIMEOUT == 120.0
    assert clean.SCOPES_GIT_MAX_WORKERS == 10
    assert clean.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT == 10.0


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
    timeout=0 op would not have exercised the gap this test guards).
    """
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


def test_scopes_git_max_workers_description_is_wrapped():
    import opal_server.config as cfg_mod

    lines = pathlib.Path(cfg_mod.__file__).read_text().splitlines()
    start = next(
        i for i, l in enumerate(lines) if "SCOPES_GIT_MAX_WORKERS = confi.int(" in l
    )
    block, depth = [], 0
    for line in lines[start:]:
        block.append(line)
        depth += line.count("(") - line.count(")")
        if depth == 0:
            break
    too_long = [l for l in block if len(l) > 100]
    assert not too_long, f"unwrapped lines: {too_long}"
    assert OpalServerConfig(prefix="OPAL_").SCOPES_GIT_MAX_WORKERS == 10


from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitConcurrencyLimitExceeded,
    _mark_git_op_done,
    _mark_git_op_started,
    git_busy_count,
)


def test_max_zombies_default(monkeypatch):
    monkeypatch.delenv("OPAL_SCOPES_GIT_MAX_ZOMBIES", raising=False)
    monkeypatch.delenv("OPAL_SCOPES_GIT_MAX_WORKERS", raising=False)
    assert OpalServerConfig(prefix="OPAL_").SCOPES_GIT_MAX_ZOMBIES == 40


@pytest.mark.asyncio
async def test_zombie_cap_refuses_new_op(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_ZOMBIES", 2)
    _mark_git_op_started("z1")
    _mark_git_op_started("z2")
    try:
        assert git_busy_count() == 2
        with pytest.raises(GitConcurrencyLimitExceeded):
            await run_in_git_executor(lambda: 1, timeout=5)
    finally:
        _mark_git_op_done("z1")
        _mark_git_op_done("z2")


@pytest.mark.asyncio
async def test_op_admitted_below_zombie_cap(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_ZOMBIES", 2)
    _mark_git_op_started("z1")
    try:
        assert await run_in_git_executor(lambda: 7, timeout=5) == 7
    finally:
        _mark_git_op_done("z1")


@pytest.mark.asyncio
async def test_negative_max_zombies_is_treated_as_no_cap(monkeypatch):
    """0 means "no cap"; a NEGATIVE value must too.

    Unclamped, a negative is truthy and `git_busy_count() >= cap` holds
    with nothing in flight, so the very first git op is refused: every
    clone and fetch raises GitConcurrencyLimitExceeded, no scope ever
    syncs, policy goes stale fleet-wide, and the one error line
    misdirects on-call to "remotes appear stuck" when nothing is stuck.
    Every sibling knob in this subsystem is clamped; this one is now
    too.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_ZOMBIES", -1)
    assert git_busy_count() == 0
    assert await run_in_git_executor(lambda: 7, timeout=5) == 7

    # ...and it stays uncapped with ops already in flight.
    _mark_git_op_started("neg-1")
    try:
        assert await run_in_git_executor(lambda: 8, timeout=5) == 8
    finally:
        _mark_git_op_done("neg-1")


from concurrent.futures import ThreadPoolExecutor

from opal_server.git_fetcher import _DaemonThreadPoolExecutor


def test_adjust_thread_count_falls_back_on_worker_shape_mismatch(monkeypatch):
    ex = _DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="shape-test")
    try:
        monkeypatch.setattr(
            cf_thread, "_worker", lambda a, b, c: None
        )  # wrong arity (3)
        called = {"super": False}
        monkeypatch.setattr(
            ThreadPoolExecutor,
            "_adjust_thread_count",
            lambda self: called.__setitem__("super", True),
        )
        ex._adjust_thread_count()  # must not raise
        assert called["super"] is True
    finally:
        ex.shutdown(wait=False)


def test_after_fork_child_reset_reinits_held_lock_without_deadlock():
    import opal_server.git_fetcher as gf
    from opal_server.git_fetcher import (
        _mark_git_op_done,
        _mark_git_op_started,
        _reset_git_executor_after_fork,
        git_op_in_flight,
    )

    _mark_git_op_started("stale-child-sid")
    done = threading.Event()

    def _run_child_handler():
        _reset_git_executor_after_fork()
        done.set()

    worker = threading.Thread(target=_run_child_handler, daemon=True)
    gf._git_busy_lock.acquire()  # emulate the 'before' handler holding it at fork
    try:
        worker.start()
        assert done.wait(2), "child reset deadlocked on the inherited-held lock"
        assert gf._git_busy_lock.acquire(timeout=1), "lock still held after child reset"
        gf._git_busy_lock.release()
        assert git_op_in_flight("stale-child-sid") is False
    finally:
        _mark_git_op_done("stale-child-sid")


def test_reset_caches_skips_free_for_in_flight_source():
    from opal_server.git_fetcher import (
        GitPolicyFetcher,
        _mark_git_op_done,
        _mark_git_op_started,
    )

    freed = []

    class _Handle:
        def __init__(self, name):
            self.name = name

        def free(self):
            freed.append(self.name)

    busy_path = "/base/git_sources/busysha-0"
    free_path = "/base/git_sources/freesha-1"
    try:
        GitPolicyFetcher.repos[busy_path] = _Handle("busy")
        GitPolicyFetcher.repos[free_path] = _Handle("free")
        _mark_git_op_started("busysha-0")  # basename(busy_path) == source_id
        GitPolicyFetcher.reset_caches()
        assert freed == ["free"], f"in-flight handle was freed: {freed}"
        assert not GitPolicyFetcher.repos
    finally:
        _mark_git_op_done("busysha-0")
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.repo_locks.clear()


def test_pre_fork_shutdown_keeps_busy_marker_child_reset_clears_it():
    from opal_server.git_fetcher import (
        _mark_git_op_done,
        _mark_git_op_started,
        _reset_git_executor_after_fork,
        git_op_in_flight,
        shutdown_git_executor,
    )

    _mark_git_op_started("survive-sid")
    try:
        shutdown_git_executor()
        assert git_op_in_flight("survive-sid") is True  # survives pre-fork teardown
        _reset_git_executor_after_fork()
        assert git_op_in_flight("survive-sid") is False
    finally:
        _mark_git_op_done("survive-sid")


def test_drain_git_ops_returns_true_when_no_ops():
    from opal_server.git_fetcher import drain_git_ops

    assert drain_git_ops(1.0) is True


def test_drain_git_ops_times_out_while_op_in_flight():
    from opal_server.git_fetcher import (
        _mark_git_op_done,
        _mark_git_op_started,
        drain_git_ops,
    )

    _mark_git_op_started("stuck-sid")
    try:
        start = time.monotonic()
        assert drain_git_ops(0.3) is False
        assert 0.3 <= time.monotonic() - start < 1.5
    finally:
        _mark_git_op_done("stuck-sid")


def test_drain_git_ops_returns_as_soon_as_last_op_clears():
    from opal_server.git_fetcher import (
        _mark_git_op_done,
        _mark_git_op_started,
        drain_git_ops,
    )

    _mark_git_op_started("clears-sid")

    def _clear():
        time.sleep(0.1)
        _mark_git_op_done("clears-sid")

    t = threading.Thread(target=_clear, daemon=True)
    t.start()
    try:
        start = time.monotonic()
        assert drain_git_ops(5.0) is True
        assert time.monotonic() - start < 2.0
    finally:
        t.join(2)


# --- Sync-path single-flight guard (fetch_and_notify_on_changes): while a
# prior timed-out git op is still marked in-flight for a source, the next sync
# must SKIP the whole pass rather than touch the non-thread-safe Repository
# concurrently. Deleting the guard makes both mutations ship green (it also caps
# the phase-2 duplicate re-fetch storm), so it needs its own coverage. ---
from opal_common.schemas.policy_source import (  # noqa: E402
    GitPolicyScopeSource,
    NoAuthData,
)
from opal_server.git_fetcher import (  # noqa: E402
    GitPolicyFetcher,
    _mark_git_op_done,
    _mark_git_op_started,
)


class _ReachedDiscover(Exception):
    """Raised from a stubbed _discover_repository to prove execution passed the
    in-flight guard (the first real op after it)."""


def _guard_fetcher(tmp_path, monkeypatch):
    src = GitPolicyScopeSource(
        source_type="git",
        url="https://git/guard.git",
        branch="main",
        auth=NoAuthData(auth_type="none"),
    )
    fetcher = GitPolicyFetcher(tmp_path, "s1", src)

    def _boom(_path):
        raise _ReachedDiscover

    # _discover_repository is the first thing the method does after the guard;
    # raising here stops before any real git work while signalling "reached".
    monkeypatch.setattr(fetcher, "_discover_repository", _boom)
    return fetcher


@pytest.mark.asyncio
async def test_fetch_and_notify_skips_when_git_op_in_flight(tmp_path, monkeypatch):
    fetcher = _guard_fetcher(tmp_path, monkeypatch)
    _mark_git_op_started(fetcher._source_id)
    try:
        # Guard must fire -> return before _discover_repository -> no _ReachedDiscover.
        await fetcher.fetch_and_notify_on_changes()
    finally:
        _mark_git_op_done(fetcher._source_id)


@pytest.mark.asyncio
async def test_fetch_and_notify_proceeds_when_nothing_in_flight(tmp_path, monkeypatch):
    # Inverse: with no in-flight marker the guard must NOT fire, so work reaches
    # _discover_repository — otherwise the guard would be a no-op that always skips.
    fetcher = _guard_fetcher(tmp_path, monkeypatch)
    with pytest.raises(_ReachedDiscover):
        await fetcher.fetch_and_notify_on_changes()
