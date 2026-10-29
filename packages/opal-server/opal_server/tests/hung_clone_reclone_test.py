"""SCOPES_GIT_RECLONE_HUNG_ON_START: a fetch or clone that outlives its timeout
leaves a marker beside its clone for as long as it lingers, and any later
successful fetch or clone of that source removes it; a server start deletes each
marked clone before the preload's sync, which clones it fresh."""
import asyncio
import fcntl
import os
import subprocess
import threading
from pathlib import Path

import opal_common.logger as opal_common_logger
import opal_server.git_fetcher as git_fetcher_module
import opal_server.scopes.purge as purge_module
import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    SOURCE_ID_RE,
    GitPolicyFetcher,
    hung_marker_path,
    reclone_hung_scope_clones,
    run_in_git_executor,
)


def _sid(n: int, shard: int = 0) -> str:
    return f"{n:064x}-{shard}"


def _root(base: Path) -> Path:
    return GitPolicyFetcher.base_dir(base)


def _clone_dir(base: Path, name: str, *, hung=False) -> Path:
    clone = _root(base) / name
    (clone / ".git").mkdir(parents=True)
    (clone / ".git" / "FETCH_HEAD").write_text("x\n")
    if hung:
        hung_marker_path(clone).write_text("")
    return clone


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


async def _until(predicate, timeout=5.0):
    """Bounded poll for a condition another thread sets."""

    async def _wait():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_wait(), timeout)


def test_marker_sits_beside_the_clone():
    clone = Path("/x/git_sources") / _sid(1)
    assert hung_marker_path(clone) == Path("/x/git_sources") / f"{_sid(1)}.hung"


def test_purge_validates_ids_with_the_same_pattern():
    assert purge_module._SOURCE_ID_RE is SOURCE_ID_RE
    assert SOURCE_ID_RE.match(_sid(1)) and not SOURCE_ID_RE.match(_sid(1) + "\n")


# --- the marker, in run_in_git_executor ------------------------------------------------


@pytest.mark.asyncio
async def test_an_op_past_its_timeout_marks_until_it_returns(tmp_path):
    marker = tmp_path / "m.hung"
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, busy_key="k1", hung_marker=marker
        )
    assert marker.exists()  # the op is still running
    release.set()
    await _until(lambda: not marker.exists())


@pytest.mark.asyncio
async def test_a_failing_op_past_its_timeout_still_clears_its_marker(tmp_path):
    marker = tmp_path / "m.hung"
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
async def test_an_op_within_its_timeout_leaves_no_marker(tmp_path):
    marker = tmp_path / "m.hung"
    assert await run_in_git_executor(lambda: 42, timeout=5, hung_marker=marker) == 42
    assert not marker.exists()


@pytest.mark.asyncio
async def test_no_marker_without_hung_marker(tmp_path):
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(release.wait, 5, timeout=0.05)
    release.set()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_an_unwritable_marker_is_logged_not_raised(tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    marker = blocker / "m.hung"  # its parent is a file: cannot be created
    release = threading.Event()
    with pytest.raises(TimeoutError):  # the op's own timeout, nothing else
        await run_in_git_executor(release.wait, 5, timeout=0.05, hung_marker=marker)
    release.set()


@pytest.mark.asyncio
async def test_the_marker_is_written_off_the_event_loop(tmp_path, monkeypatch):
    marker = tmp_path / "m.hung"
    loop_thread = threading.get_ident()
    writers = []
    real_touch = Path.touch

    def _touch(self, *a, **k):
        writers.append(threading.get_ident())
        return real_touch(self, *a, **k)

    monkeypatch.setattr(Path, "touch", _touch)
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(release.wait, 5, timeout=0.05, hung_marker=marker)
    release.set()
    assert writers and loop_thread not in writers


# --- the marker, through a real scope fetch and clone ----------------------------------------


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


def _fetcher(tmp_path):
    source = GitPolicyScopeSource(
        source_type="git",
        url=str(_origin(tmp_path)),
        branch="main",
        auth=NoAuthData(auth_type="none"),
    )
    base = tmp_path / "base"
    return GitPolicyFetcher(base, "scope-1", source), GitPolicyFetcher.repo_clone_path(
        base, source
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_a_hung_fetch_marks_its_clone_only_when_enabled(
    tmp_path, monkeypatch, enabled
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_RECLONE_HUNG_ON_START", enabled)
    fetcher, clone = _fetcher(tmp_path)
    await fetcher.fetch_and_notify_on_changes()  # clones
    release = threading.Event()
    monkeypatch.setattr(
        pygit2.remotes.Remote, "fetch", lambda self, *a, **k: release.wait(5)
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.05)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)  # times out
    assert hung_marker_path(clone).exists() is enabled
    release.set()
    await _until(lambda: not hung_marker_path(clone).exists())


@pytest.mark.asyncio
async def test_a_hung_clone_marks_its_clone_path(tmp_path, monkeypatch, on):
    fetcher, clone = _fetcher(tmp_path)
    release = threading.Event()
    monkeypatch.setattr(
        git_fetcher_module, "clone_repository", lambda *a, **k: release.wait(5)
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.05)
    await fetcher.fetch_and_notify_on_changes()  # the clone times out
    assert hung_marker_path(clone).exists()
    release.set()
    await _until(lambda: not hung_marker_path(clone).exists())


@pytest.mark.asyncio
async def test_a_later_successful_fetch_clears_a_marker_from_another_process(
    tmp_path, on
):
    """The process whose op hung died (a worker recycled, say): the marker it
    left must not outlive the next good fetch."""
    fetcher, clone = _fetcher(tmp_path)
    await fetcher.fetch_and_notify_on_changes()  # clones
    hung_marker_path(clone).write_text("")
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert not hung_marker_path(clone).exists()


@pytest.mark.asyncio
async def test_a_successful_clone_clears_a_leftover_marker(tmp_path, on):
    fetcher, clone = _fetcher(tmp_path)
    clone.parent.mkdir(parents=True)
    hung_marker_path(clone).write_text("")
    await fetcher.fetch_and_notify_on_changes()  # clones
    assert not hung_marker_path(clone).exists()


# --- the start-time sweep ------------------------------------------------------------------


def test_off_by_default_and_touches_nothing(tmp_path, monkeypatch):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)

    def _no_disk(*a, **k):
        raise AssertionError("disabled: must not touch the disk")

    monkeypatch.setattr(git_fetcher_module, "_take_repack_lock", _no_disk)
    assert opal_server_config.SCOPES_GIT_RECLONE_HUNG_ON_START is False
    assert reclone_hung_scope_clones(tmp_path) == 0
    assert hung.exists()


def test_deletes_only_marked_clones(tmp_path, on, monkeypatch):
    seen = []
    monkeypatch.setattr(
        git_fetcher_module.metrics, "increment", lambda name, *a, **k: seen.append(name)
    )
    hung = _clone_dir(tmp_path, _sid(1, 0), hung=True)
    healthy = _clone_dir(tmp_path, _sid(1, 1))
    assert reclone_hung_scope_clones(tmp_path) == 1
    assert not hung.exists() and not hung_marker_path(hung).exists()
    assert healthy.exists()
    assert seen == ["opal_server.scopes.hung_clone_recloned"]


def test_a_marker_without_its_clone_is_just_removed(tmp_path, on):
    """A scope deleted since: no orphan clone comes back."""
    _root(tmp_path).mkdir(parents=True)
    marker = _root(tmp_path) / f"{_sid(1)}.hung"
    marker.write_text("")
    assert reclone_hung_scope_clones(tmp_path) == 0
    assert not marker.exists()
    assert list(_root(tmp_path).iterdir()) == []


def test_ignores_what_is_not_a_marker_of_a_real_clone_dir(tmp_path, on):
    root = _root(tmp_path)
    target = _clone_dir(tmp_path, "elsewhere")
    link = root / _sid(2)
    link.symlink_to(target, target_is_directory=True)
    (root / f"{_sid(2)}.hung").write_text("")  # marker of a symlink
    (root / "not-a-source-id.hung").write_text("")
    newline = _clone_dir(tmp_path, _sid(3) + "\n")
    (root / f"{_sid(3)}\n.hung").write_text("")
    assert reclone_hung_scope_clones(tmp_path) == 0
    for p in (target, link, newline, root / f"{_sid(2)}.hung"):
        assert p.exists(), p


def test_missing_root_is_a_new_pod(tmp_path, on):
    assert reclone_hung_scope_clones(tmp_path / "nowhere") == 0


def test_does_nothing_while_a_repack_holds_the_lock(tmp_path, on):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)
    fd = os.open(_root(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert reclone_hung_scope_clones(tmp_path) == 0
        assert hung.exists() and hung_marker_path(hung).exists()
    finally:
        os.close(fd)


def test_a_failed_delete_keeps_the_marker_for_the_next_start(tmp_path, on, monkeypatch):
    stuck = _clone_dir(tmp_path, _sid(1, 0), hung=True)
    other = _clone_dir(tmp_path, _sid(1, 1), hung=True)
    real = git_fetcher_module.shutil.rmtree

    def _rmtree(path, *a, **k):
        if Path(path) == stuck:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *a, **k)

    monkeypatch.setattr(git_fetcher_module.shutil, "rmtree", _rmtree)
    assert reclone_hung_scope_clones(tmp_path) == 1
    assert stuck.exists() and hung_marker_path(stuck).exists()
    assert not other.exists() and not hung_marker_path(other).exists()


def test_an_unlistable_root_is_logged_not_raised(tmp_path, on, monkeypatch):
    _clone_dir(tmp_path, _sid(1), hung=True)

    def _denied(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(git_fetcher_module.os, "scandir", _denied)
    assert reclone_hung_scope_clones(tmp_path) == 0


# --- the preload wiring ---------------------------------------------------------------------


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

    real = task_module.reclone_hung_scope_clones

    def _sweep(base_dir):
        state["events"].append("sweep")
        return real(base_dir)

    monkeypatch.setattr(task_module, "ScopesService", _Service)
    monkeypatch.setattr(task_module, "reclone_hung_scope_clones", _sweep)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda timeout: True)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    state["run"] = task_module.ScopesPolicyWatcherTask.preload_scopes
    return state


def test_preload_sweeps_before_it_syncs(preload):
    preload["run"]()
    assert preload["events"] == ["sweep", "sync_scopes"]


def test_preload_end_to_end(tmp_path, on, preload):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)
    healthy = _clone_dir(tmp_path, _sid(2))
    at_sync = {}
    preload["sync"] = lambda: at_sync.update(
        hung=hung.exists(), healthy=healthy.exists()
    )
    preload["run"]()
    assert at_sync == {"hung": False, "healthy": True}


def test_no_preload_when_scopes_are_off(preload, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    preload["run"]()
    assert preload["events"] == []
