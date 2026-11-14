"""A sync that finds a git op of this process still running on its clone.

A libgit2 op keeps running on its thread after its timeout, and a git
command-line op counts as running until git has been stopped. A sync
that is not part of a sync pass (a refresh, a PUT /scopes, the sync a
bundle request asks for) and finds such an op waits up to that op's own
timeout for it to end (SCOPES_GIT_CLONE_TIMEOUT for a git command-line
clone, SCOPES_GIT_FETCH_TIMEOUT for a fetch), then syncs once more, so
the refresh it carries is not lost. A pass's sync skips the clone as
before: the next pass syncs it.
"""

import asyncio
import threading
import time
import weakref

import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server import git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_cli import clone_timeout
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    PolicyFetcherCallbacks,
    _mark_git_op_done,
    _mark_git_op_started,
    _reset_git_executor_after_fork,
    git_op_in_flight,
    run_git_cli_op,
    wait_for_git_op_gone,
)

# A libgit2 op lingers past its timeout on its thread; the git command-line case
# pins its own backend.
pytestmark = pytest.mark.fetch_backend("libgit2")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(git_fetcher, "_op_gone_waiters", {})
    monkeypatch.setattr(git_fetcher, "_git_op_timeouts", {})
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 5.0)


def _fetcher(tmp_path, url="https://git/retry.git", branch="main"):
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch=branch,
        auth=NoAuthData(auth_type="none"),
    )
    return GitPolicyFetcher(tmp_path, "s1", source, callbacks=_Updates())


class _Updates(PolicyFetcherCallbacks):
    def __init__(self):
        self.updates = []

    async def on_update(self, old_head, head):
        self.updates.append((old_head, head))


def _record_sync_once(fetcher, monkeypatch):
    """Replace _sync_once with a recorder that skips exactly when an op of this
    process is in flight on the clone, as the real one does."""
    calls = []

    async def _sync_once(*args, **kwargs):
        skipped = git_op_in_flight(fetcher.clone_source_id)
        calls.append(skipped)
        return skipped

    monkeypatch.setattr(fetcher, "_sync_once", _sync_once)
    return calls


@pytest.mark.asyncio
async def test_an_explicit_sync_skipped_behind_a_running_op_runs_once_it_ends(
    tmp_path, monkeypatch
):
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    sid = fetcher.clone_source_id
    _mark_git_op_started(sid)
    task = asyncio.create_task(fetcher.fetch_and_notify_on_changes(force_fetch=True))
    await asyncio.sleep(0.05)
    assert calls == [True]
    assert not task.done(), "gave up instead of waiting for the op to end"

    threading.Thread(target=_mark_git_op_done, args=(sid,)).start()
    await asyncio.wait_for(task, 2)
    assert calls == [True, False]


@pytest.mark.asyncio
async def test_a_pass_sync_skipped_behind_a_running_op_is_not_retried(
    tmp_path, monkeypatch
):
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    sid = fetcher.clone_source_id
    _mark_git_op_started(sid)
    try:
        started = time.monotonic()
        with GitPolicyFetcher.sync_pass():
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)
        assert calls == [True]
        assert time.monotonic() - started < 1, "a pass's sync waited for the op"
    finally:
        _mark_git_op_done(sid)


@pytest.mark.asyncio
async def test_no_retry_when_the_op_outlives_the_fetch_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    sid = fetcher.clone_source_id
    _mark_git_op_started(sid)
    try:
        started = time.monotonic()
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)
        elapsed = time.monotonic() - started
    finally:
        _mark_git_op_done(sid)
    assert calls == [True]
    assert 0.15 <= elapsed < 1
    assert git_fetcher._op_gone_waiters == {}, "the timed-out wait left its waiter"


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf")])
@pytest.mark.asyncio
async def test_no_wait_without_a_finite_fetch_timeout(tmp_path, monkeypatch, timeout):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", timeout)
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    sid = fetcher.clone_source_id
    _mark_git_op_started(sid)
    try:
        await asyncio.wait_for(
            fetcher.fetch_and_notify_on_changes(force_fetch=True), timeout=1
        )
    finally:
        _mark_git_op_done(sid)
    assert calls == [True]


@pytest.mark.asyncio
async def test_a_sync_that_was_not_skipped_does_not_wait(tmp_path, monkeypatch):
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    await asyncio.wait_for(fetcher.fetch_and_notify_on_changes(), timeout=1)
    assert calls == [False]


@pytest.mark.asyncio
async def test_wait_for_git_op_gone(monkeypatch):
    assert await wait_for_git_op_gone("idle", 0.01) is True

    _mark_git_op_started("busy")
    try:
        assert await wait_for_git_op_gone("busy", 0.05) is False
        assert git_fetcher._op_gone_waiters == {}
        waiter = asyncio.create_task(wait_for_git_op_gone("busy", 5))
        await asyncio.sleep(0.02)
        assert len(git_fetcher._op_gone_waiters["busy"]) == 1
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert git_fetcher._op_gone_waiters == {}, "a cancelled wait left its waiter"
    finally:
        _mark_git_op_done("busy")


def test_op_done_after_its_waiters_loop_closed_raises_nothing():
    """A waiter whose event loop has closed (its worker shut down while it
    waited) must not fail the op's thread when the op ends."""
    loop = asyncio.new_event_loop()
    gone = loop.create_future()
    loop.close()
    _mark_git_op_started("closed-loop")
    git_fetcher._op_gone_waiters["closed-loop"] = [(loop, gone)]
    _mark_git_op_done("closed-loop")
    assert git_fetcher._op_gone_waiters == {}


def test_fork_handler_drops_op_gone_waiters(monkeypatch):
    """The fork handler runs here, in the test process, so every global it
    resets is swapped for a stand-in first (see git_repack_test)."""
    busy_lock = threading.Lock()
    busy_lock.acquire()  # the 'before' fork handler holds it across fork
    monkeypatch.setattr(git_fetcher, "_git_busy_lock", busy_lock)
    monkeypatch.setattr(git_fetcher, "_git_busy", set())
    monkeypatch.setattr(git_fetcher, "_repack_lock", threading.Lock())
    monkeypatch.setattr(git_fetcher, "_repack_lock_fds", set())
    monkeypatch.setattr(
        git_fetcher, "_live_ops_semaphores", weakref.WeakKeyDictionary()
    )
    git_fetcher._op_gone_waiters["inherited"] = [(None, None)]
    git_fetcher._git_op_timeouts["inherited"] = 120.0

    _reset_git_executor_after_fork()

    assert git_fetcher._op_gone_waiters == {}
    assert git_fetcher._git_op_timeouts == {}


def _commit(origin, branch, text):
    sig = pygit2.Signature("opal-test", "opal-test@example.com")
    blob = origin.create_blob(text.encode())
    builder = origin.TreeBuilder()
    builder.insert("policy.rego", blob, pygit2.GIT_FILEMODE_BLOB)
    ref = f"refs/heads/{branch}"
    parents = [origin.references[ref].target] if ref in origin.references else []
    return str(origin.create_commit(ref, sig, sig, text, builder.write(), parents))


def _remote_ref(fetcher, branch):
    repo = pygit2.Repository(str(fetcher._repo_path))
    try:
        return str(repo.references[f"refs/remotes/origin/{branch}"].target)
    finally:
        repo.free()


@pytest.mark.asyncio
async def test_a_refresh_behind_a_lingering_libgit2_fetch_fetches_after_it(tmp_path):
    """Real clone of a local origin; the lingering op is a marker set by hand
    (a libgit2 fetch past its timeout holds it until its thread returns)."""
    origin = pygit2.init_repository(str(tmp_path / "origin"), bare=True)
    _commit(origin, "main", "package p\n")
    fetcher = _fetcher(tmp_path / "base", url=str(tmp_path / "origin"))
    await fetcher.fetch_and_notify_on_changes()
    new_head = _commit(origin, "main", "package p\n# two\n")

    sid = fetcher.clone_source_id
    _mark_git_op_started(sid)
    refresh = asyncio.create_task(fetcher.fetch_and_notify_on_changes(force_fetch=True))
    await asyncio.sleep(0.1)
    assert _remote_ref(fetcher, "main") != new_head, "fetched beside the running op"

    threading.Thread(target=_mark_git_op_done, args=(sid,)).start()
    await asyncio.wait_for(refresh, 10)
    assert _remote_ref(fetcher, "main") == new_head
    assert fetcher.callbacks.updates[-1][1] == new_head


@pytest.mark.fetch_backend("cli")
@pytest.mark.asyncio
async def test_a_cli_sync_behind_a_stopping_op_does_not_wait_past_its_stop(
    tmp_path, monkeypatch
):
    """A git command-line op counts as running until git has been stopped (its
    on_gone), which can be after the op returned.

    The wait ends when that stop does, not at SCOPES_GIT_FETCH_TIMEOUT.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 30.0)
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    sid = fetcher.clone_source_id
    stopped = asyncio.Event()
    gone = {}

    async def _stopping_op(on_gone):
        # Returned at its timeout; git's process group is still being stopped.
        gone["call"] = on_gone

    await run_git_cli_op(_stopping_op, timeout=30.0, busy_key=sid)
    assert git_op_in_flight(sid)

    async def _stop_later():
        await asyncio.sleep(0.2)
        gone["call"](False)
        stopped.set()

    stopper = asyncio.create_task(_stop_later())
    started = time.monotonic()
    await asyncio.wait_for(fetcher.fetch_and_notify_on_changes(force_fetch=True), 5)
    elapsed = time.monotonic() - started
    await stopper

    assert stopped.is_set()
    assert calls == [True, False]
    assert elapsed < 2, f"waited {elapsed:.1f}s, past the op's stop"


async def _start_cli_op(sid, timeout, runs_for):
    """A git command-line op on ``sid``'s clone, started with ``timeout``, that
    stays in flight for ``runs_for`` seconds; once it is in flight."""

    async def _op(on_gone):
        await asyncio.sleep(runs_for)
        on_gone(True)

    task = asyncio.create_task(run_git_cli_op(_op, timeout=timeout, busy_key=sid))
    while not git_op_in_flight(sid):
        await asyncio.sleep(0.01)
    return task


@pytest.mark.fetch_backend("cli")
@pytest.mark.asyncio
async def test_a_refresh_behind_a_clone_waits_up_to_the_clone_timeout(
    tmp_path, monkeypatch
):
    """A git command-line clone has SCOPES_GIT_CLONE_TIMEOUT, longer than a
    fetch's: a refresh skipped behind one still syncs once the clone ends,
    after SCOPES_GIT_FETCH_TIMEOUT has passed."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 5.0)
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    clone = await _start_cli_op(fetcher.clone_source_id, clone_timeout(), 0.6)

    await asyncio.wait_for(fetcher.fetch_and_notify_on_changes(force_fetch=True), 5)
    await clone

    assert calls == [True, False]


@pytest.mark.fetch_backend("cli")
@pytest.mark.asyncio
async def test_a_refresh_behind_a_fetch_waits_up_to_the_fetch_timeout(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 5.0)
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    fetch = await _start_cli_op(fetcher.clone_source_id, 0.2, 1.0)
    try:
        started = time.monotonic()
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)
        elapsed = time.monotonic() - started
    finally:
        await fetch

    assert calls == [True]
    assert 0.15 <= elapsed < 0.9


@pytest.mark.fetch_backend("cli")
@pytest.mark.asyncio
async def test_no_wait_behind_a_clone_with_no_clone_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 5.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 0.0)
    fetcher = _fetcher(tmp_path)
    calls = _record_sync_once(fetcher, monkeypatch)
    clone = await _start_cli_op(fetcher.clone_source_id, clone_timeout(), 1.0)
    try:
        started = time.monotonic()
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)
        elapsed = time.monotonic() - started
    finally:
        await clone

    assert calls == [True]
    assert elapsed < 0.5
