"""SCOPES_GIT_RECLONE_HUNG_ON_START: a fetch that outlives its timeout leaves a
marker in its clone for as long as it lingers; a server start moves each
marked clone aside before the preload's sync, so the sync clones it fresh, then
deletes the old copy or, when the clone was not redone, moves it back."""
import asyncio
import datetime
import fcntl
import os
import subprocess
import threading
import time
from pathlib import Path

import opal_common.logger as opal_common_logger
import opal_server.git_fetcher as git_fetcher_module
import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    QuarantinedClone,
    quarantine_hung_scope_clones,
    run_in_git_executor,
    settle_quarantined_clones,
)

MARKER = "opal-fetch-hung"


def _sid(n: int, shard: int = 0) -> str:
    return f"{n:064x}-{shard}"


def _clone_dir(base: Path, name: str, *, complete=True, hung=False) -> Path:
    """A directory that looks like a scope clone."""
    git_dir = GitPolicyFetcher.base_dir(base) / name / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    if complete:
        (git_dir / "FETCH_HEAD").write_text("x\n")
    if hung:
        (git_dir / MARKER).write_text("")
    return git_dir.parent


@pytest.fixture(autouse=True)
def _clean_fetcher_state():
    for d in (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
    ):
        d.clear()
    yield
    for d in (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
    ):
        d.clear()


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_RECLONE_HUNG_ON_START", True)


@pytest.fixture
def outcomes(monkeypatch):
    seen = []
    monkeypatch.setattr(
        git_fetcher_module.metrics,
        "increment",
        lambda name, *a, tags=None, **k: seen.append(
            (name, (tags or {}).get("outcome"))
        ),
    )
    return seen


async def _until(predicate, timeout=5.0):
    """Bounded poll for a condition another thread sets."""

    async def _wait():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_wait(), timeout)


# --- the marker, in run_in_git_executor ---------------------------------------------


@pytest.mark.asyncio
async def test_an_op_past_its_timeout_marks_until_it_returns(tmp_path):
    marker = tmp_path / MARKER
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, busy_key="k1", hung_marker=marker
        )
    assert marker.exists()  # the op is still running
    release.set()
    await _until(lambda: not marker.exists())


@pytest.mark.asyncio
async def test_an_op_within_its_timeout_leaves_no_marker(tmp_path):
    marker = tmp_path / MARKER
    assert await run_in_git_executor(lambda: 42, timeout=5, hung_marker=marker) == 42
    assert not marker.exists()


@pytest.mark.asyncio
async def test_a_failing_op_past_its_timeout_still_clears_its_marker(tmp_path):
    marker = tmp_path / MARKER
    release = threading.Event()

    def _fails():
        release.wait(5)
        raise pygit2.GitError("remote hung up")

    with pytest.raises(TimeoutError):
        await run_in_git_executor(_fails, timeout=0.05, hung_marker=marker)
    assert marker.exists()
    release.set()
    await _until(lambda: not marker.exists())


@pytest.mark.asyncio
async def test_no_marker_without_hung_marker(tmp_path):
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(release.wait, 5, timeout=0.05)
    release.set()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_an_unwritable_marker_is_logged_not_raised_past_the_timeout(tmp_path):
    marker = tmp_path / "missing-dir" / MARKER
    release = threading.Event()
    with pytest.raises(TimeoutError):  # the op's own timeout, nothing else
        await run_in_git_executor(release.wait, 5, timeout=0.05, hung_marker=marker)
    release.set()


# --- the marker, through a real fetch ------------------------------------------------


def _origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin)], check=True)
    for args in (
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["commit", "-q", "--allow-empty", "-m", "c1"],
    ):
        subprocess.run(["git", "-C", str(origin), *args], check=True)
    return origin


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_a_hung_scope_fetch_marks_its_clone_only_when_enabled(
    tmp_path, monkeypatch, enabled
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_RECLONE_HUNG_ON_START", enabled)
    source = GitPolicyScopeSource(
        source_type="git",
        url=str(_origin(tmp_path)),
        branch="main",
        auth=NoAuthData(auth_type="none"),
    )
    base = tmp_path / "base"
    fetcher = GitPolicyFetcher(base, "scope-1", source)
    await fetcher.fetch_and_notify_on_changes()  # clones
    clone = GitPolicyFetcher.repo_clone_path(base, source)
    assert (clone / ".git" / "FETCH_HEAD").exists()

    release = threading.Event()
    monkeypatch.setattr(
        pygit2.remotes.Remote, "fetch", lambda self, *a, **k: release.wait(5)
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.05)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)  # times out
    marker = clone / ".git" / MARKER
    assert marker.exists() is enabled
    release.set()
    await _until(lambda: not marker.exists())


# --- quarantine before the sync -------------------------------------------------------


def test_off_by_default_and_touches_nothing(tmp_path, monkeypatch):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)

    def _no_disk(*a, **k):
        raise AssertionError("disabled: must not touch the disk")

    monkeypatch.setattr(git_fetcher_module, "_take_repack_lock", _no_disk)
    assert opal_server_config.SCOPES_GIT_RECLONE_HUNG_ON_START is False
    assert quarantine_hung_scope_clones(tmp_path) == []
    assert hung.exists()


def test_moves_only_marked_clones(tmp_path, on):
    hung = _clone_dir(tmp_path, _sid(1, 0), hung=True)
    healthy = _clone_dir(tmp_path, _sid(1, 1))
    (q,) = quarantine_hung_scope_clones(tmp_path)
    assert q.source_id == _sid(1, 0) and q.clone == hung
    assert not hung.exists() and q.trash.is_dir() and healthy.exists()
    assert q.trash.name == f".hung-{_sid(1, 0)}"
    assert isinstance(q.since, datetime.datetime)


def test_ignores_what_is_not_a_real_clone_dir(tmp_path, on):
    root = GitPolicyFetcher.base_dir(tmp_path)
    odd = _clone_dir(tmp_path, _sid(1) + "\n", hung=True)  # not a source id
    target = _clone_dir(tmp_path, "elsewhere", hung=True)
    link = root / _sid(2)
    link.symlink_to(target, target_is_directory=True)
    a_file = root / _sid(3)
    a_file.write_text("")
    assert quarantine_hung_scope_clones(tmp_path) == []
    for p in (odd, target, link, a_file):
        assert p.exists(), p


def test_missing_root_is_a_new_pod(tmp_path, on):
    assert quarantine_hung_scope_clones(tmp_path / "nowhere") == []


def test_does_nothing_while_a_repack_holds_the_lock(tmp_path, on):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)
    fd = os.open(GitPolicyFetcher.base_dir(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert quarantine_hung_scope_clones(tmp_path) == []
        assert hung.exists()
    finally:
        os.close(fd)


def test_a_failed_move_keeps_the_clone(tmp_path, on, monkeypatch):
    stuck = _clone_dir(tmp_path, _sid(1, 0), hung=True)
    other = _clone_dir(tmp_path, _sid(1, 1), hung=True)
    real = os.rename

    def _rename(src, dst):
        if Path(src) == stuck:
            raise PermissionError(13, "Permission denied", str(src))
        return real(src, dst)

    monkeypatch.setattr(git_fetcher_module.os, "rename", _rename)
    moved = quarantine_hung_scope_clones(tmp_path)
    assert [q.source_id for q in moved] == [_sid(1, 1)]
    assert stuck.exists() and not other.exists()


def test_an_unlistable_root_is_logged_not_raised(tmp_path, on, monkeypatch):
    _clone_dir(tmp_path, _sid(1), hung=True)

    def _denied(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(git_fetcher_module.os, "scandir", _denied)
    assert quarantine_hung_scope_clones(tmp_path) == []


# --- leftovers of an earlier start -------------------------------------------------------


def test_a_leftover_is_deleted_once_its_clone_is_complete(tmp_path, on):
    root = GitPolicyFetcher.base_dir(tmp_path)
    clone = _clone_dir(tmp_path, _sid(1))
    leftover = root / f".hung-{_sid(1)}"
    (leftover / ".git").mkdir(parents=True)
    assert quarantine_hung_scope_clones(tmp_path) == []
    assert not leftover.exists() and clone.exists()


@pytest.mark.parametrize("state", ["missing", "partial", "hung"])
def test_a_leftover_is_put_back_when_its_clone_is_not_complete(tmp_path, on, state):
    """The start that moved it died mid-sync, or its clone was still running
    and then failed: the old copy is the only good one."""
    root = GitPolicyFetcher.base_dir(tmp_path)
    leftover = root / f".hung-{_sid(1)}"
    (leftover / ".git").mkdir(parents=True)
    (leftover / ".git" / "FETCH_HEAD").write_text("old\n")
    (leftover / ".git" / MARKER).write_text("")
    if state == "partial":
        _clone_dir(tmp_path, _sid(1), complete=False)
    elif state == "hung":
        _clone_dir(tmp_path, _sid(1), hung=True)
    moved = quarantine_hung_scope_clones(tmp_path)
    clone = root / _sid(1)
    if state == "hung":
        # Put back (marker dropped), then judged on its own: not hung any more.
        assert moved == []
    assert not leftover.exists()
    assert (clone / ".git" / "FETCH_HEAD").read_text() == "old\n"
    assert not (clone / ".git" / MARKER).exists()


# --- settle after the sync ----------------------------------------------------------------


def _moved(tmp_path) -> QuarantinedClone:
    _clone_dir(tmp_path, _sid(1), hung=True)
    (q,) = quarantine_hung_scope_clones(tmp_path)
    return q


def test_recloned_deletes_the_old_copy(tmp_path, on, outcomes):
    q = _moved(tmp_path)
    _clone_dir(tmp_path, q.source_id)  # the sync's fresh clone
    GitPolicyFetcher.repos_last_fetched[q.source_id] = datetime.datetime.now()
    settle_quarantined_clones([q])
    assert q.clone.exists() and not q.trash.exists()
    assert outcomes == [("opal_server.scopes.hung_clone", "recloned")]


def test_a_success_recorded_before_the_move_does_not_count(tmp_path, on, outcomes):
    GitPolicyFetcher.repos_last_fetched[_sid(1)] = datetime.datetime.now()
    time.sleep(0.01)
    q = _moved(tmp_path)
    settle_quarantined_clones([q])
    assert outcomes[-1][1] == "restored"


@pytest.mark.parametrize("partial", [False, True])
def test_not_recloned_puts_the_old_copy_back(tmp_path, on, outcomes, partial):
    q = _moved(tmp_path)
    if partial:
        _clone_dir(tmp_path, q.source_id, complete=False)
    settle_quarantined_clones([q])
    assert not q.trash.exists()
    git_dir = q.clone / ".git"
    assert (git_dir / "FETCH_HEAD").exists() and not (git_dir / MARKER).exists()
    assert outcomes == [("opal_server.scopes.hung_clone", "restored")]


def test_in_flight_leaves_both_for_the_next_start(tmp_path, on, outcomes, monkeypatch):
    q = _moved(tmp_path)
    live = _clone_dir(tmp_path, q.source_id, complete=False)
    monkeypatch.setattr(
        git_fetcher_module, "git_op_in_flight", lambda k: k == q.source_id
    )
    settle_quarantined_clones([q])
    assert live.exists() and q.trash.exists()
    assert outcomes == [("opal_server.scopes.hung_clone", "in_flight")]


def test_settle_never_raises_and_reports_lost(tmp_path, on, outcomes, monkeypatch):
    q = _moved(tmp_path)

    def _boom(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(git_fetcher_module.os, "rename", _boom)
    settle_quarantined_clones([q])
    assert q.trash.exists()  # still there for the next start
    assert outcomes == [("opal_server.scopes.hung_clone", "lost")]


# --- the preload wiring -----------------------------------------------------------------


@pytest.fixture
def preload(monkeypatch, tmp_path):
    state = {"events": [], "sync": None}
    monkeypatch.setattr(opal_common_logger, "_logs_configured", True)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    monkeypatch.setattr(task_module, "RedisDB", lambda url: object())
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: object())

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            state["events"].append("sync_scopes")
            if state["sync"]:
                state["sync"]()

    real_q, real_s = (
        task_module.quarantine_hung_scope_clones,
        task_module.settle_quarantined_clones,
    )

    def _q(base_dir):
        state["events"].append("quarantine")
        return real_q(base_dir)

    def _s(moved):
        state["events"].append("settle")
        real_s(moved)

    monkeypatch.setattr(task_module, "ScopesService", _Service)
    monkeypatch.setattr(task_module, "quarantine_hung_scope_clones", _q)
    monkeypatch.setattr(task_module, "settle_quarantined_clones", _s)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda timeout: True)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    state["run"] = task_module.ScopesPolicyWatcherTask.preload_scopes
    return state


def test_preload_order_is_quarantine_sync_settle(preload):
    preload["run"]()
    assert preload["events"] == ["quarantine", "sync_scopes", "settle"]


def test_preload_end_to_end(tmp_path, on, preload):
    """Two marked clones: the sync clones one again and not the other. A
    healthy clone is never touched."""
    root = GitPolicyFetcher.base_dir(tmp_path)
    _clone_dir(tmp_path, _sid(1), hung=True)
    _clone_dir(tmp_path, _sid(2), hung=True)
    healthy = _clone_dir(tmp_path, _sid(3))
    at_sync = {}

    def _sync():
        at_sync.update({n: (root / _sid(n)).exists() for n in (1, 2, 3)})
        _clone_dir(tmp_path, _sid(1))  # cloned again
        GitPolicyFetcher.repos_last_fetched[_sid(1)] = datetime.datetime.now()

    preload["sync"] = _sync
    preload["run"]()
    assert at_sync == {1: False, 2: False, 3: True}
    for n in (1, 2, 3):
        assert not ((root / _sid(n)) / ".git" / MARKER).exists(), n
    assert not any(p.name.startswith(".hung-") for p in root.iterdir())
    assert healthy.exists()


def test_preload_settles_even_when_the_sync_raises(tmp_path, on, preload):
    _clone_dir(tmp_path, _sid(1), hung=True)

    def _sync():
        raise RuntimeError("redis went away")

    preload["sync"] = _sync
    with pytest.raises(RuntimeError):
        preload["run"]()
    assert preload["events"][-1] == "settle"
    assert (
        GitPolicyFetcher.base_dir(tmp_path) / _sid(1) / ".git" / "FETCH_HEAD"
    ).exists()


def test_no_preload_when_scopes_are_off(preload, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    preload["run"]()
    assert preload["events"] == []


# --- the libgit2 behaviour "complete clone" relies on -----------------------------------


def test_libgit2_clone_writes_fetch_head(tmp_path):
    repo = pygit2.clone_repository(str(_origin(tmp_path)), str(tmp_path / "c"))
    assert (tmp_path / "c" / ".git" / "FETCH_HEAD").is_file()
    repo.free()
