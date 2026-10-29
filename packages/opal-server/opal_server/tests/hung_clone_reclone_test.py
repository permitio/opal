"""SCOPES_GIT_RECLONE_HUNG_ON_START: a fetch or clone that outlives its timeout
leaves a marker of its own beside its clone for as long as it lingers, and any
later successful fetch or clone of that source removes them all; a server start
deletes each clone this host left marked before the preload's sync, which clones
it fresh."""
import asyncio
import fcntl
import itertools
import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

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
    clear_hung_markers,
    hung_marker_dir,
    reclone_hung_scope_clones,
    run_in_git_executor,
)

HOST = git_fetcher_module._HUNG_MARKER_HOST


def _sid(n: int, shard: int = 0) -> str:
    return f"{n:064x}-{shard}"


def _root(base: Path) -> Path:
    return GitPolicyFetcher.base_dir(base)


def _mark(clone: Path, host: str = None) -> Path:
    d = hung_marker_dir(clone)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{host or HOST}-1234-0"
    f.write_text("")
    return f


def _clone_dir(base: Path, name: str, *, hung=False) -> Path:
    clone = _root(base) / name
    (clone / ".git").mkdir(parents=True)
    (clone / ".git" / "FETCH_HEAD").write_text("x\n")
    if hung:
        _mark(clone)
    return clone


def _markers(clone: Path) -> list:
    d = hung_marker_dir(clone)
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


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


def _join_marker_threads(timeout=5.0):
    """Wait for every marker housekeeping thread to finish."""
    for t in threading.enumerate():
        if t.name == "opal-git-hung-marker":
            t.join(timeout)
            assert not t.is_alive(), "a marker thread is stuck"


@pytest.fixture
def warnings_logged():
    """The messages logged at WARNING or above while the test runs."""
    messages = []
    sink = opal_common_logger.logger.add(
        lambda m: messages.append(m.record["message"]), level="WARNING"
    )
    yield messages
    opal_common_logger.logger.remove(sink)


def test_markers_sit_beside_the_clone():
    clone = Path("/x/git_sources") / _sid(1)
    assert hung_marker_dir(clone) == Path("/x/git_sources") / f"{_sid(1)}.hung"


def test_purge_validates_ids_with_the_same_pattern():
    assert purge_module.SOURCE_ID_RE is SOURCE_ID_RE
    assert SOURCE_ID_RE.match(_sid(1)) and not SOURCE_ID_RE.match(_sid(1) + "\n")


# --- the marker, in run_in_git_executor ------------------------------------------------


@pytest.mark.asyncio
async def test_an_op_past_its_timeout_marks_until_it_returns(tmp_path):
    d = tmp_path / "m.hung"
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait,
            5,
            timeout=0.05,
            busy_key="k1",
            marker_dir=d,
            mark_when_hung=True,
        )
    await _until(lambda: d.is_dir() and any(d.iterdir()))  # the op still runs
    (marker,) = list(d.iterdir())
    assert marker.name.startswith(f"{HOST}-{os.getpid()}-")
    release.set()
    await _until(lambda: not marker.exists())


@pytest.mark.asyncio
async def test_a_failing_op_past_its_timeout_still_clears_its_marker(tmp_path):
    d = tmp_path / "m.hung"
    release = threading.Event()

    def _fails():
        release.wait(5)
        raise pygit2.GitError("remote hung up")

    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            _fails, timeout=0.05, marker_dir=d, mark_when_hung=True
        )
    await _until(lambda: d.is_dir() and any(d.iterdir()))
    release.set()
    await _until(lambda: not any(d.iterdir()))


@pytest.mark.asyncio
async def test_a_fast_failure_keeps_other_processes_markers(tmp_path):
    """Revoked credentials, a deleted repository: a marker a killed worker left
    must stay, so the next start still re-clones."""
    d = tmp_path / "m.hung"
    d.mkdir()
    (d / "other-1-0").write_text("")

    def _fails():
        raise pygit2.GitError("authentication required")

    with pytest.raises(pygit2.GitError):
        await run_in_git_executor(_fails, timeout=5, marker_dir=d, mark_when_hung=True)
    _join_marker_threads()
    assert (d / "other-1-0").exists()


@pytest.mark.asyncio
async def test_an_op_within_its_timeout_leaves_no_marker(tmp_path):
    d = tmp_path / "m.hung"
    assert (
        await run_in_git_executor(
            lambda: 42, timeout=5, marker_dir=d, mark_when_hung=True
        )
        == 42
    )
    assert not d.exists()


@pytest.mark.asyncio
async def test_no_marker_without_marker_dir(tmp_path):
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(release.wait, 5, timeout=0.05)
    release.set()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_an_unwritable_marker_is_logged_not_raised(
    tmp_path, monkeypatch, warnings_logged
):
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    d = blocker / "m.hung"  # its parent is a file: cannot be created
    raised = []
    monkeypatch.setattr(threading, "excepthook", lambda a: raised.append(a.exc_value))
    release = threading.Event()
    with pytest.raises(TimeoutError):  # the op's own timeout, nothing else
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, marker_dir=d, mark_when_hung=True
        )
    await _until(
        lambda: any("Could not write hung-op marker" in m for m in warnings_logged)
    )
    _join_marker_threads()
    release.set()
    assert raised == []  # the marker thread logged, it did not raise


@pytest.mark.asyncio
async def test_a_stalled_marker_write_delays_neither_the_timeout_nor_the_slot(
    tmp_path, monkeypatch
):
    """The volume the marker sits on may be what is stalled: the timeout must
    raise on time, the live-op slot be freed, and the write happen off the
    event loop."""
    d = tmp_path / "m.hung"
    loop_thread = threading.get_ident()
    writers, resume_write = [], threading.Event()
    real_touch = Path.touch

    def _stalled_touch(self, *a, **k):
        writers.append(threading.get_ident())
        resume_write.wait(5)
        return real_touch(self, *a, **k)

    monkeypatch.setattr(Path, "touch", _stalled_touch)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 1)
    git_fetcher_module._live_ops_semaphores.clear()
    release = threading.Event()
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, marker_dir=d, mark_when_hung=True
        )
    assert time.monotonic() - t0 < 2
    # The single slot is free again: another op runs while the write stalls.
    assert (
        await asyncio.wait_for(
            run_in_git_executor(lambda: "next", timeout=5), timeout=2
        )
        == "next"
    )
    await _until(lambda: writers)
    assert loop_thread not in writers
    resume_write.set()
    release.set()
    git_fetcher_module._live_ops_semaphores.clear()


@pytest.mark.asyncio
async def test_one_op_returning_does_not_clear_another_ops_marker(tmp_path):
    d = tmp_path / "m.hung"
    first, second = threading.Event(), threading.Event()
    for ev in (first, second):
        with pytest.raises(TimeoutError):
            await run_in_git_executor(
                ev.wait, 5, timeout=0.05, marker_dir=d, mark_when_hung=True
            )
    await _until(lambda: d.is_dir() and len(list(d.iterdir())) == 2)
    first.set()
    await _until(lambda: len(list(d.iterdir())) == 1)
    second.set()
    await _until(lambda: not any(d.iterdir()))


@pytest.mark.asyncio
async def test_a_successful_op_clears_markers_without_marking(tmp_path):
    d = tmp_path / "m.hung"
    d.mkdir()
    (d / "other-1-0").write_text("")
    assert await run_in_git_executor(lambda: "ok", timeout=5, marker_dir=d) == "ok"
    await _until(lambda: not d.exists())  # removed on a thread of its own


@pytest.mark.asyncio
async def test_no_marker_without_mark_when_hung(tmp_path):
    d = tmp_path / "m.hung"
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, busy_key="k-nomark", marker_dir=d
        )
    release.set()
    # Once the op has returned and every marker thread has finished.
    await _until(lambda: not git_fetcher_module.git_op_in_flight("k-nomark"))
    _join_marker_threads()
    assert not d.exists()


@pytest.mark.asyncio
async def test_a_late_success_removes_only_its_own_marker(tmp_path):
    """An op that timed out and then succeeded proves little about the other
    hung ops on the clone: their markers stay."""
    d = tmp_path / "m.hung"
    d.mkdir()
    other = d / "other-1-0"
    other.write_text("")
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, marker_dir=d, mark_when_hung=True
        )
    await _until(lambda: len(list(d.iterdir())) == 2)
    release.set()  # returns True: a success, but after its timeout
    await _until(lambda: len(list(d.iterdir())) == 1)
    assert other.exists()


@pytest.mark.asyncio
async def test_a_stalled_marker_write_never_blocks_the_ops_own_thread(
    tmp_path, monkeypatch
):
    """The op returns while its marker write is stuck on the volume: the op's
    thread still finishes (the lock never covers file I/O), and the marker,
    once written, is removed since the op had already returned."""
    d = tmp_path / "m.hung"
    write_started, resume_write = threading.Event(), threading.Event()
    real_touch = Path.touch

    def _slow_touch(self, *a, **k):
        write_started.set()
        resume_write.wait(5)
        return real_touch(self, *a, **k)

    monkeypatch.setattr(Path, "touch", _slow_touch)
    op_finished = asyncio.Event()
    real_consume = git_fetcher_module._consume_future_result

    def _consume(fut):  # the op future's done-callback, on the event loop
        op_finished.set()
        return real_consume(fut)

    monkeypatch.setattr(git_fetcher_module, "_consume_future_result", _consume)
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, marker_dir=d, mark_when_hung=True
        )
    await _until(write_started.is_set)
    release.set()
    await asyncio.wait_for(op_finished.wait(), 2)  # while the write is stuck
    assert not resume_write.is_set()
    resume_write.set()
    # The dir exists and is empty while the write is stuck, so wait for the
    # marker thread itself: it writes the file, sees the op returned and
    # removes it again.
    _join_marker_threads()
    assert d.is_dir() and not any(d.iterdir())


@pytest.mark.asyncio
async def test_a_failed_marker_thread_start_keeps_the_ops_outcome(
    tmp_path, monkeypatch, warnings_logged
):
    """At the process's thread limit the housekeeping thread cannot start: the
    op's result and its TimeoutError stand all the same."""
    real_start = threading.Thread.start

    def _start(self):
        if self.name == "opal-git-hung-marker":
            raise RuntimeError("can't start new thread")
        return real_start(self)

    monkeypatch.setattr(threading.Thread, "start", _start)
    d = tmp_path / "m.hung"
    d.mkdir()
    (d / "other-1-0").write_text("")
    assert await run_in_git_executor(lambda: "ok", timeout=5, marker_dir=d) == "ok"
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, marker_dir=d, mark_when_hung=True
        )
    release.set()
    started = [m for m in warnings_logged if "Could not start a thread to" in m]
    assert len(started) == 2
    # The hang's marker is a file inside d, so pin each path exactly.
    assert any(f"clear the stale hung-op markers in {d}: " in m for m in started)
    assert any(f"record the hang of this op in {d}{os.sep}" in m for m in started)


@pytest.mark.asyncio
async def test_a_marker_that_cannot_be_removed_is_logged(
    tmp_path, monkeypatch, warnings_logged
):
    d = tmp_path / "m.hung"
    release = threading.Event()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            release.wait, 5, timeout=0.05, marker_dir=d, mark_when_hung=True
        )
    await _until(lambda: d.is_dir() and any(d.iterdir()))

    def _denied(self, *a, **k):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "unlink", _denied)
    release.set()
    await _until(
        lambda: any("Could not remove hung-op marker" in m for m in warnings_logged)
    )


def test_marker_names_differ_across_a_restart_in_place(monkeypatch):
    """Same host, same pid, the sequence starting over: still another name."""
    monkeypatch.setattr(git_fetcher_module, "_hung_marker_seq", itertools.count())
    first = git_fetcher_module._hung_marker_name()
    monkeypatch.setattr(git_fetcher_module, "_hung_marker_seq", itertools.count())
    again = git_fetcher_module._hung_marker_name()
    assert first.startswith(f"{HOST}-{os.getpid()}-0-") and first != again


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
    if enabled:
        await _until(lambda: _markers(clone))
    else:
        assert _markers(clone) == []
    release.set()
    await _until(lambda: not _markers(clone))


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_a_hung_clone_marks_its_clone_path_only_when_enabled(
    tmp_path, monkeypatch, enabled
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_RECLONE_HUNG_ON_START", enabled)
    fetcher, clone = _fetcher(tmp_path)
    release = threading.Event()
    monkeypatch.setattr(
        git_fetcher_module, "clone_repository", lambda *a, **k: release.wait(5)
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.05)
    await fetcher.fetch_and_notify_on_changes()  # the clone times out
    if enabled:
        await _until(lambda: _markers(clone))
    else:
        _join_marker_threads()
        assert _markers(clone) == []
    release.set()
    await _until(lambda: not _markers(clone))


@pytest.mark.asyncio
async def test_a_later_successful_fetch_clears_a_marker_from_another_process(
    tmp_path, on
):
    """The process whose op hung died (a worker recycled, say): the marker it
    left must not outlive the next good fetch."""
    fetcher, clone = _fetcher(tmp_path)
    await fetcher.fetch_and_notify_on_changes()  # clones
    _mark(clone, host="other-host")
    _mark(clone)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    await _until(
        lambda: not hung_marker_dir(clone).exists()
    )  # cleared on its own thread


@pytest.mark.asyncio
async def test_a_successful_clone_clears_leftover_markers(tmp_path, on):
    fetcher, clone = _fetcher(tmp_path)
    _mark(clone)
    await fetcher.fetch_and_notify_on_changes()  # clones
    await _until(
        lambda: not hung_marker_dir(clone).exists()
    )  # cleared on its own thread


@pytest.mark.asyncio
async def test_markers_are_cleared_even_with_the_setting_off(tmp_path):
    """Markers left while it was on must not outlive a good fetch made while it
    is off, or turning it on again deletes a healthy clone."""
    fetcher, clone = _fetcher(tmp_path)
    await fetcher.fetch_and_notify_on_changes()  # clones
    _mark(clone)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    await _until(
        lambda: not hung_marker_dir(clone).exists()
    )  # cleared on its own thread


def test_clear_hung_markers_retries_when_an_entry_vanishes_mid_walk(
    tmp_path, monkeypatch
):
    """Python 3.10-3.12 rmtree stops with FileNotFoundError when an entry it
    listed is removed first, leaving the rest."""
    clone = _clone_dir(tmp_path, _sid(1), hung=True)
    real = git_fetcher_module.shutil.rmtree
    calls = []

    def _vanishing(path, *a, **k):
        calls.append(path)
        if len(calls) == 1:
            raise FileNotFoundError(2, "No such file", str(Path(path) / "gone"))
        return real(path, *a, **k)

    monkeypatch.setattr(git_fetcher_module.shutil, "rmtree", _vanishing)
    clear_hung_markers(hung_marker_dir(clone))
    assert len(calls) == 2 and not hung_marker_dir(clone).exists()


def test_clear_hung_markers_warns_when_the_retry_fails_too(
    tmp_path, monkeypatch, warnings_logged
):
    clone = _clone_dir(tmp_path, _sid(1), hung=True)

    calls = []

    def _vanishing(path, *a, **k):
        calls.append(path)
        raise FileNotFoundError(2, "No such file", str(Path(path) / "gone"))

    monkeypatch.setattr(git_fetcher_module.shutil, "rmtree", _vanishing)
    clear_hung_markers(hung_marker_dir(clone))
    assert len(calls) == 2  # one retry, no more
    assert any("Could not remove hung-op markers" in m for m in warnings_logged)


def test_clear_hung_markers_on_a_dir_already_gone_is_quiet(tmp_path, warnings_logged):
    """Another process removed it first: nothing to do, nothing to warn."""
    clear_hung_markers(tmp_path / "gone.hung")
    assert warnings_logged == []


def test_clear_hung_markers_never_raises(tmp_path, monkeypatch):
    clone = _clone_dir(tmp_path, _sid(1), hung=True)

    def _denied(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(git_fetcher_module.shutil, "rmtree", _denied)
    clear_hung_markers(clone)
    clear_hung_markers(tmp_path / "nothing")


# --- the start-time sweep ------------------------------------------------------------------


def test_off_by_default_never_deletes_a_clone(tmp_path, monkeypatch):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)

    def _no_disk(*a, **k):
        raise AssertionError("disabled: must not take the lock to delete clones")

    monkeypatch.setattr(git_fetcher_module, "_take_repack_lock", _no_disk)
    assert opal_server_config.SCOPES_GIT_RECLONE_HUNG_ON_START is False
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert hung.exists()


def test_deletes_only_marked_clones(tmp_path, on, monkeypatch):
    seen = []
    monkeypatch.setattr(
        git_fetcher_module.metrics, "increment", lambda name, *a, **k: seen.append(name)
    )
    hung = _clone_dir(tmp_path, _sid(1, 0), hung=True)
    healthy = _clone_dir(tmp_path, _sid(1, 1))
    assert reclone_hung_scope_clones(tmp_path, None) == 1
    assert not hung.exists() and not hung_marker_dir(hung).exists()
    assert healthy.exists()
    assert seen == ["opal_server.scopes.hung_clone_recloned"]
    # The repack lock is free again: the master must not carry it across fork.
    fd = os.open(_root(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def test_any_markers_count_whoever_wrote_them(tmp_path, on):
    """Sharing BASE_DIR between running servers is not supported, so a marker
    left by the previous pod on a reused volume counts too."""
    clone = _clone_dir(tmp_path, _sid(1))
    _mark(clone, host="previous-pod")
    assert reclone_hung_scope_clones(tmp_path, None) == 1
    assert not clone.exists() and not hung_marker_dir(clone).exists()


def test_an_empty_marker_dir_is_just_removed(tmp_path, on):
    clone = _clone_dir(tmp_path, _sid(1))
    hung_marker_dir(clone).mkdir()
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert clone.exists() and not hung_marker_dir(clone).exists()


def test_a_marker_without_its_clone_is_just_removed(tmp_path, on):
    """A scope deleted since: no orphan clone comes back."""
    _mark(_root(tmp_path) / _sid(1))
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert list(_root(tmp_path).iterdir()) == []


def test_markers_of_a_symlinked_clone_never_delete_it(tmp_path, on):
    target = _clone_dir(tmp_path, "elsewhere")
    link = _root(tmp_path) / _sid(2)
    link.symlink_to(target, target_is_directory=True)
    _mark(link)
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert target.exists() and link.exists()
    assert _markers(link)  # kept: a clone it cannot delete keeps its markers


def test_a_marker_dir_that_is_a_symlink_is_ignored(tmp_path, on):
    clone = _clone_dir(tmp_path, _sid(1))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "planted-1-0").write_text("")
    hung_marker_dir(clone).symlink_to(elsewhere, target_is_directory=True)
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert clone.exists() and (elsewhere / "planted-1-0").exists()


def test_a_marker_of_a_name_that_is_not_a_source_id_is_ignored(tmp_path, on):
    clone = _clone_dir(tmp_path, "not-a-source-id", hung=True)
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert clone.exists() and _markers(clone)


def test_a_source_id_with_a_trailing_newline_is_ignored(tmp_path, on):
    clone = _clone_dir(tmp_path, _sid(3) + "\n", hung=True)
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert clone.exists() and _markers(clone)


def test_a_file_where_the_marker_dir_would_be_is_ignored(tmp_path, on):
    clone = _clone_dir(tmp_path, _sid(4))
    as_file = _root(tmp_path) / f"{_sid(4)}.hung"
    as_file.write_text("")
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert clone.exists() and as_file.exists()


def test_a_clone_that_cannot_be_statted_is_logged_not_raised(
    tmp_path, on, monkeypatch, warnings_logged
):
    """A raise here would stop the gunicorn master from starting."""
    clone = _clone_dir(tmp_path, _sid(1), hung=True)
    real = Path.is_symlink

    def _eio(self):
        if self == clone:
            raise OSError(5, "Input/output error", str(self))
        return real(self)

    monkeypatch.setattr(Path, "is_symlink", _eio)
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert clone.exists() and _markers(clone)
    assert any("Could not delete hung scope clone" in m for m in warnings_logged)


def test_missing_root_is_a_new_pod(tmp_path, on):
    assert reclone_hung_scope_clones(tmp_path / "nowhere", None) == 0


def test_does_nothing_while_a_repack_holds_the_lock(tmp_path, on):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)
    fd = os.open(_root(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert reclone_hung_scope_clones(tmp_path, None) == 0
        assert hung.exists() and _markers(hung)
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
    assert reclone_hung_scope_clones(tmp_path, None) == 1
    assert stuck.exists() and _markers(stuck)
    assert not other.exists() and not hung_marker_dir(other).exists()


def test_an_unlistable_root_is_logged_not_raised(tmp_path, on, monkeypatch):
    _clone_dir(tmp_path, _sid(1), hung=True)

    def _denied(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(git_fetcher_module.os, "scandir", _denied)
    assert reclone_hung_scope_clones(tmp_path, None) == 0


def test_with_the_setting_off_a_start_removes_every_marker(tmp_path):
    hung = _clone_dir(tmp_path, _sid(1), hung=True)
    _mark(_root(tmp_path) / _sid(2))  # a deleted scope's
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert hung.exists()  # never deleted with the setting off
    assert not hung_marker_dir(hung).exists()
    assert not hung_marker_dir(_root(tmp_path) / _sid(2)).exists()


def test_markers_of_a_deleted_scope_are_removed(tmp_path, on):
    gone = _root(tmp_path) / _sid(1)
    _mark(gone, host="old-pod")
    _clone_dir(tmp_path, _sid(2))  # git_sources exists with something in it
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert not hung_marker_dir(gone).exists()


def test_a_partly_deleted_clone_keeps_its_markers(tmp_path, on, monkeypatch):
    clone = _clone_dir(tmp_path, _sid(1), hung=True)

    def _vanishing_entry(path, *a, **k):
        raise FileNotFoundError(2, "No such file", str(Path(path) / ".git" / "x"))

    monkeypatch.setattr(git_fetcher_module.shutil, "rmtree", _vanishing_entry)
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    assert clone.exists() and _markers(clone)


def test_a_non_positive_fetch_timeout_is_warned_about(
    tmp_path, on, monkeypatch, warnings_logged
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0)
    _clone_dir(tmp_path, _sid(1), hung=True)
    assert reclone_hung_scope_clones(tmp_path, None) == 1  # still acts on what it finds
    assert any("is not positive" in m for m in warnings_logged)


# --- the provider-wide guard ------------------------------------------------------------


def test_one_repo_hung_across_its_shards_is_recloned(tmp_path, on):
    """A single big repository on 3 shards, among other healthy
    repositories."""
    for shard in range(3):
        _clone_dir(tmp_path, _sid(1, shard), hung=True)
    for n in range(2, 4):
        _clone_dir(tmp_path, _sid(n))
    # 1 of 3 repositories; counted per shard it would be 3 of 5, an outage.
    assert reclone_hung_scope_clones(tmp_path, None) == 3


def test_a_single_repo_deployment_is_recloned(tmp_path, on):
    _clone_dir(tmp_path, _sid(1), hung=True)
    assert reclone_hung_scope_clones(tmp_path, None) == 1


def test_a_provider_wide_hang_keeps_every_clone(tmp_path, on):
    """Most repositories hung at once: likely the provider, keep stale policy."""
    for n in (1, 2, 3):
        _clone_dir(tmp_path, _sid(n), hung=True)
    healthy = _clone_dir(tmp_path, _sid(4))
    assert reclone_hung_scope_clones(tmp_path, None) == 0
    for n in (1, 2, 3):
        clone = _root(tmp_path) / _sid(n)
        assert clone.exists() and _markers(clone)
    assert healthy.exists()


@pytest.mark.parametrize(
    "hung, total, recloned",
    [
        (2, 4, 0),  # both comparisons at equality: an outage
        (2, 3, 0),
        (2, 5, 2),  # under half: two repositories of their own
    ],
)
def test_the_provider_wide_guard_boundaries(tmp_path, on, hung, total, recloned):
    for n in range(total):
        _clone_dir(tmp_path, _sid(n), hung=n < hung)
    assert reclone_hung_scope_clones(tmp_path, None) == recloned


def test_clones_no_scope_uses_do_not_dilute_the_guard(tmp_path, on):
    """Two live repositories hung by an outage, beside three leftover dirs of
    repointed scopes: still an outage, both clones kept."""
    live = {_sid(1), _sid(2)}
    for s in live:
        _clone_dir(tmp_path, s, hung=True)
    for n in (3, 4, 5):
        _clone_dir(tmp_path, _sid(n))
    assert reclone_hung_scope_clones(tmp_path, live) == 0
    assert all((_root(tmp_path) / s).exists() for s in live)


def test_hung_clones_no_scope_uses_are_deleted_but_never_count(tmp_path, on):
    """Over every dir, 3 hung of 6 would read as an outage; over the live ones
    it is 1 of 4, so all three hung clones go."""
    live = {_sid(n) for n in (1, 2, 3, 4)}
    _clone_dir(tmp_path, _sid(1), hung=True)
    for n in (2, 3, 4):
        _clone_dir(tmp_path, _sid(n))
    for n in (5, 6):
        _clone_dir(tmp_path, _sid(n), hung=True)
    assert reclone_hung_scope_clones(tmp_path, live) == 3


def test_hung_leftovers_beside_healthy_live_clones_are_deleted(tmp_path, on):
    live = {_sid(1), _sid(2)}
    for s in live:
        _clone_dir(tmp_path, s)
    leftovers = [_clone_dir(tmp_path, _sid(n), hung=True) for n in (5, 6)]
    assert reclone_hung_scope_clones(tmp_path, live) == 2
    for c in leftovers:
        assert not c.exists() and not hung_marker_dir(c).exists()
    assert all((_root(tmp_path) / s).exists() for s in live)


def test_live_sources_without_a_clone_do_not_dilute_the_guard(tmp_path, on):
    """Five live sources, two cloned, both hung: an outage, counted from the
    clones on disk."""
    live = {_sid(n) for n in range(1, 6)}
    for n in (1, 2):
        _clone_dir(tmp_path, _sid(n), hung=True)
    assert reclone_hung_scope_clones(tmp_path, live) == 0


@pytest.mark.parametrize("live", [set(), {_sid(99)}])
def test_no_live_clone_on_disk_keeps_every_hung_clone(
    tmp_path, on, live, warnings_logged
):
    """An empty scope list (a store being repopulated, say) must not turn the
    guard off: a scope that comes back during an outage still has its clone."""
    for n in (1, 2, 3):
        _clone_dir(tmp_path, _sid(n), hung=True)
    assert reclone_hung_scope_clones(tmp_path, live) == 0
    assert all((_root(tmp_path) / _sid(n)).exists() for n in (1, 2, 3))
    assert any("none is a clone of a current scope" in m for m in warnings_logged)


# --- the preload wiring ---------------------------------------------------------------------


@pytest.fixture
def preload(monkeypatch, tmp_path):
    state = {
        "events": [],
        "sync": None,
        "scopes": [],
        "live": [],
        "loops": [],
        "reads": 0,
    }
    monkeypatch.setattr(opal_common_logger, "_logs_configured", True)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    monkeypatch.setattr(task_module, "RedisDB", lambda url: object())

    class _Scopes:
        def __init__(self, db):
            pass

        async def all(self):
            state["reads"] += 1
            state["loops"].append(asyncio.get_running_loop())
            return state["scopes"]

    monkeypatch.setattr(task_module, "ScopeRepository", _Scopes)

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            state["loops"].append(asyncio.get_running_loop())
            state["events"].append("sync_scopes")
            if state["sync"]:
                state["sync"]()

    real = task_module.reclone_hung_scope_clones

    def _sweep(base_dir, live_source_ids):
        state["events"].append("sweep")
        state["live"].append(live_source_ids)
        return real(base_dir, live_source_ids)

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
    policies = [
        SimpleNamespace(url=f"https://example.com/{n}.git", branch="main")
        for n in (1, 2)
    ]
    preload["scopes"] = [SimpleNamespace(policy=p) for p in policies]
    hung, healthy = (
        _clone_dir(tmp_path, GitPolicyFetcher.source_id(p), hung=h)
        for p, h in zip(policies, (True, False))
    )
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


def test_preload_reads_the_scopes_and_syncs_in_one_event_loop(on, preload):
    """The Redis client binds its connections to the loop that first uses
    them: reading the scopes in one asyncio.run and syncing in another fails
    at a real start."""
    preload["run"]()
    first, second = preload["loops"]
    assert first is second


def test_preload_reads_no_scopes_with_the_setting_off(preload):
    preload["run"]()
    assert preload["live"] == [None]
    assert preload["reads"] == 0  # the sync stub reads none either


def test_preload_counts_only_the_scopes_sources(on, preload):
    policy = SimpleNamespace(url="https://example.com/r.git", branch="main")
    preload["scopes"] = [SimpleNamespace(policy=policy)]
    preload["run"]()
    assert preload["live"] == [{GitPolicyFetcher.source_id(policy)}]
