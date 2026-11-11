"""How long a git command-line op (``opal_server.git_cli``) holds its clone,
and what is left when it ends some other way than by returning: the clone
lock every process of an op holds, a second op or process that finds it
held, the worker that dies with git running, the caller that is cancelled
(at any point, once or twice), the event loop that ends mid-stop, and the
pre-fork preload's sweep of what earlier processes left. On asyncio and on
uvloop, which the server's workers run.

Real git against local remotes only (see git_cli_test).
"""

import asyncio
import asyncio.base_subprocess
import errno
import logging
import os
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from functools import partial
from pathlib import Path
from typing import Optional

import opal_common.logger as opal_common_logger
import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import (
    GitPolicyScopeSource,
    NoAuthData,
    SSHAuthData,
)
from opal_common.tests.log_capture import capture_records
from opal_server import git_cli
from opal_server import git_fetcher as git_fetcher_module
from opal_server.config import opal_server_config
from opal_server.git_cli import (
    GitCliBusyError,
    GitCliError,
    GitCliLocalError,
    GitCliTimeoutError,
    cli_clone,
    cli_fetch,
    clone_lock_path,
    sweep_clone_leftovers,
)
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    PolicyFetcherCallbacks,
    drain_git_ops,
    git_op_in_flight,
    run_git_cli_op,
)
from opal_server.tests.git_repack_test import _flock_fails_with

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

_LOOPS = pytest.mark.parametrize("loop", ["asyncio", "uvloop"])


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)


def _source(url: str) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git", url=url, branch="master", auth=NoAuthData(auth_type="none")
    )


class _Recorder(PolicyFetcherCallbacks):
    async def on_update(self, old_head, head):
        pass


def _run(loop: str, main):
    """Run ``main()`` on a new event loop of this kind, then end the loop as
    asyncio.run does: cancel every task left, let them finish, close it."""
    if loop == "uvloop":
        new_loop = pytest.importorskip("uvloop").new_event_loop()
    else:
        new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        return new_loop.run_until_complete(main())
    finally:
        try:
            left = asyncio.all_tasks(new_loop)
            for task in left:
                task.cancel()
            new_loop.run_until_complete(asyncio.gather(*left, return_exceptions=True))
            new_loop.run_until_complete(new_loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            new_loop.close()


# How long a test waits for what it acts on to be ready (a git, a shim, a
# survivor started): long enough for a slow, loaded CI runner. Bounds on
# what a test proves are its own.
_READY_SECONDS = 30.0
# An op timeout long enough for git to have started a shim before it is
# stopped, on such a runner too; the shim blocks git for good, so the timeout
# is what stops it.
_SHIM_TIMEOUT = 10.0


async def _until(predicate, timeout=_READY_SECONDS, interval=0.02):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition never held"
        await asyncio.sleep(interval)


def _wait_until(predicate, timeout=_READY_SECONDS):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition never held"
        time.sleep(0.02)


def _clone_at(path: Path, origin_url: str, url: str) -> None:
    """A clone of ``origin_url`` (by libgit2) at ``path`` whose remote is
    ``url``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pygit2.clone_repository(origin_url, str(path)).free()
    _point_at(path, url)


def _point_at(clone: Path, url: str) -> None:
    repo = pygit2.Repository(str(clone))
    try:
        repo.remotes.set_url("origin", url)
    finally:
        repo.free()


def _refs(path: Path) -> dict:
    repo = pygit2.Repository(str(path))
    try:
        return {
            name: str(repo.references[name].resolve().target)
            for name in repo.references
            if name.startswith("refs/remotes/") and not name.endswith("/HEAD")
        }
    finally:
        repo.free()


def _lock_is_free(clone: Path) -> bool:
    fd = git_cli.take_clone_lock(clone)
    if fd is None:
        return False
    git_cli.drop_clone_lock(fd)
    return True


def _plant_leftovers(clone: Path) -> list:
    """What a git killed mid-fetch leaves: a ref lock, packed-refs.lock and
    a partial pack."""
    git_dir = clone / ".git"
    left = [
        git_dir / "refs" / "remotes" / "origin" / "master.lock",
        git_dir / "packed-refs.lock",
        git_dir / "objects" / "pack" / "tmp_pack_Ab12Cd",
    ]
    for path in left:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    return left


def _ssh_shim(tmp_path: Path, monkeypatch, body: str) -> Path:
    """An ``ssh`` first on PATH that runs ``body`` (sh); a file it writes once
    it runs (``started``, where body puts it)."""
    shims = tmp_path / "bin"
    shims.mkdir(exist_ok=True)
    ssh = shims / "ssh"
    ssh.write_text(f"#!/bin/sh\n{body}\n")
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    return shims / "ssh.started"


def _ignore_sigterm(started: Path) -> str:
    """An ssh body that ignores SIGTERM, then says so."""
    return (
        f'exec "{sys.executable}" -c "import signal, sys, time; '
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"open(sys.argv[1], 'w').close(); time.sleep(30)\" '{started}' \"$@\""
    )


def _out_of_reach(started: Path, release: Path) -> str:
    """An ssh body that moves to a session of its own (out of the group's
    reach, as a process in uninterruptible I/O is out of SIGKILL's), keeps the
    op's stderr and lock, then says so, and exits once ``release`` exists (two
    minutes at most)."""
    script = (
        "import os, sys, time\n"
        "os.setsid()\n"
        "open(sys.argv[1], 'w').close()\n"
        "deadline = time.monotonic() + 120\n"
        "while not os.path.exists(sys.argv[2]) and time.monotonic() < deadline:\n"
        "    time.sleep(0.05)\n"
    )
    return f"exec \"{sys.executable}\" -c \"{script}\" '{started}' '{release}'"


@pytest.fixture
def released_keys():
    """busy_keys a test leaves in flight on purpose (an op whose loop ended
    first), released at its end."""
    keys = []
    yield keys
    for key in keys:
        git_fetcher_module._mark_git_op_done(key)


# --- the clone lock -----------------------------------------------------------


@pytest.mark.asyncio
async def test_while_an_op_runs_no_other_op_repack_or_sweep_touches_its_clone(
    git_origin, tmp_path, blackhole, processes_with, git_groups
):
    marker = f"held-{uuid.uuid4().hex}"
    clones = tmp_path / "clones"
    clone = clones / "src"
    _clone_at(clone, git_origin.url, f"http://127.0.0.1:{blackhole}/{marker}.git")
    left = _plant_leftovers(clone)
    first = asyncio.ensure_future(
        cli_fetch(clone, "origin", _source(git_origin.url), prune=False, timeout=60)
    )
    await _until(lambda: processes_with(marker) and git_groups)
    for path in left:
        path.write_text("y")  # now the live op's own

    with pytest.raises(GitCliBusyError):
        await cli_fetch(
            clone, "origin", _source(git_origin.url), prune=False, timeout=60
        )
    with pytest.raises(GitCliBusyError):
        await cli_clone(
            git_origin.url, clone, _source(git_origin.url), remote="origin", timeout=60
        )
    with pytest.raises(GitCliBusyError):
        git_fetcher_module._repack_clone(clone, 60)
    sweep_clone_leftovers(clones)
    assert [p for p in left if not p.exists()] == []

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert [p for p in left if p.exists()] == []
    assert git_fetcher_module._repack_clone(clone, 60) is True


_ORPHAN = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from opal_server import git_cli

    fd = git_cli.take_clone_lock(Path(sys.argv[1]))
    assert fd is not None
    git_cli.mark_op_started(fd)
    print("holding", flush=True)
    sys.stdin.read()
    """
)


@pytest.fixture
def orphan(tmp_path):
    """A function: start a process that holds a clone's lock, with its pid
    recorded in the lock file, as the git of an op whose worker died does,
    until it is killed."""
    started = []

    def _start(clone: Path) -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable, "-c", _ORPHAN, str(clone)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        started.append(proc)
        assert proc.stdout is not None
        assert proc.stdout.readline() == "holding\n"
        return proc

    yield _start
    for proc in started:
        proc.kill()
        proc.communicate()


@pytest.mark.asyncio
async def test_an_orphaned_git_s_clone_is_skipped_untouched_until_it_exits(
    git_origin, tmp_path, orphan, monkeypatch
):
    """A git still running for a worker that died holds the clone's lock: a
    sync in another process skips that clone (counted, not a failure, no
    backoff) and deletes nothing of what that git is writing, and neither does
    the pre-fork sweep.

    Once it has exited, the next op finds its op unfinished, removes
    what it left, and fetches.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    emitted = []
    monkeypatch.setattr(
        metrics, "increment", lambda m, tags=None: emitted.append((m, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda m, v, tags=None: None)
    source = _source(git_origin.url)
    base = tmp_path / "base"
    fetcher = GitPolicyFetcher(base, "scope-1", source, callbacks=_Recorder())
    await fetcher.fetch_and_notify_on_changes()
    clone = GitPolicyFetcher.repo_clone_path(base, source)
    left = _plant_leftovers(clone)
    holder = orphan(clone)
    new = git_origin.commit("master")

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    sweep_clone_leftovers(clone.parent)

    assert ("opal_server.scopes.git_op_skipped", {"reason": "clone_busy"}) in emitted
    assert [m for m, _ in emitted if m == "opal_server.scopes.git_op_failures"] == []
    assert fetcher.clone_source_id not in GitPolicyFetcher.source_backoff
    assert [p for p in left if not p.exists()] == []
    assert _refs(clone)["refs/remotes/origin/master"] != new

    holder.kill()
    holder.communicate()
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert [p for p in left if p.exists()] == []
    assert _refs(clone)["refs/remotes/origin/master"] == new
    assert clone_lock_path(clone).read_bytes() == b""


_WORKER = textwrap.dedent(
    """
    import asyncio, sys
    from pathlib import Path
    from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
    from opal_server.git_cli import cli_fetch

    source = GitPolicyScopeSource(
        source_type="git", url=sys.argv[3], branch="master",
        auth=NoAuthData(auth_type="none"),
    )
    main = cli_fetch(Path(sys.argv[2]), "origin", source, prune=False, timeout=600)
    if sys.argv[1] == "uvloop":
        import uvloop
        loop = uvloop.new_event_loop()
    else:
        loop = asyncio.new_event_loop()
    loop.run_until_complete(main)
    """
)


@_LOOPS
def test_a_worker_killed_mid_fetch_takes_its_git_with_it(
    loop, git_origin, tmp_path, blackhole, processes_with
):
    """git runs in a session of its own, which no signal to the worker
    reaches: SIGKILLed (a worker timeout, an OOM kill), the worker leaves no
    one to stop it. The group ends itself as the worker's end of sh's stdin
    closes. The next op on the clone finds the dead op unfinished and
    removes what it left."""
    pytest.importorskip(loop)
    marker = f"worker-{uuid.uuid4().hex}"
    clone = tmp_path / "clones" / "src"
    url = f"http://127.0.0.1:{blackhole}/{marker}.git"
    _clone_at(clone, git_origin.url, url)
    worker = subprocess.Popen(
        [sys.executable, "-c", _WORKER, loop, str(clone), url],
        stderr=subprocess.PIPE,
    )
    try:
        _wait_until(
            lambda: any("remote-http" in a for _, _, a in processes_with(marker)),
            timeout=30,
        )
        left = _plant_leftovers(clone)

        worker.kill()
        worker.wait()
        # Long before the op's own timeout (600 s) could have ended it.
        _wait_until(lambda: processes_with(marker) == [])
    finally:
        worker.kill()
        worker.communicate()

    assert clone_lock_path(clone).read_text().strip() == str(worker.pid)
    _point_at(clone, git_origin.url)
    new = git_origin.commit("master")
    _run(
        "asyncio",
        lambda: cli_fetch(
            clone, "origin", _source(git_origin.url), prune=False, timeout=60
        ),
    )
    assert [p for p in left if p.exists()] == []
    assert _refs(clone)["refs/remotes/origin/master"] == new


# --- cancelled callers, and the end of the event loop -----------------------------


@_LOOPS
def test_a_second_cancel_while_git_is_stopped_still_kills_it_and_cleans_up(
    loop, git_origin, tmp_path, monkeypatch, processes_with, git_groups
):
    """The caller is cancelled, and cancelled again while git is in its
    SIGTERM grace: the stop goes on to SIGKILL, the clone is cleaned up, and
    only then is the op over (busy_key released)."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 3.0)
    started = _ssh_shim(
        tmp_path, monkeypatch, _ignore_sigterm(tmp_path / "bin" / "ssh.started")
    )
    marker = f"hung-{uuid.uuid4().hex}"
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, f"ssh://git@127.0.0.1:1/{marker}.git")
    stale = clone / ".git" / "packed-refs.lock"
    stale.write_text("x")
    key = f"twice-{uuid.uuid4().hex}"

    async def main():
        task = asyncio.ensure_future(
            run_git_cli_op(
                partial(
                    cli_fetch,
                    clone,
                    "origin",
                    _source(git_origin.url),
                    prune=False,
                    timeout=60,
                ),
                timeout=60,
                busy_key=key,
            )
        )
        await _until(lambda: started.exists() and git_groups)
        task.cancel()
        await asyncio.sleep(0.3)  # inside the 3 s SIGTERM grace
        assert git_op_in_flight(key)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _until(lambda: not git_op_in_flight(key))
        assert processes_with(marker) == []
        assert not stale.exists()
        # on_gone comes a step of the loop before the stop's task ends.
        await _until(lambda: git_cli.background_ops() == 0)

    _run(loop, main)


@_LOOPS
def test_a_cancelled_op_whose_git_outlives_sigkill_keeps_its_clone_until_it_exits(
    loop, git_origin, tmp_path, monkeypatch, released_keys, git_groups
):
    """As at a timeout: a member that SIGKILL does not end keeps busy_key,
    the clone's lock and what it left in the clone until it exits."""
    release = tmp_path / "release"
    started = _ssh_shim(
        tmp_path,
        monkeypatch,
        _out_of_reach(tmp_path / "bin" / "ssh.started", release),
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 0.3)
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, "ssh://git@127.0.0.1:1/survivor.git")
    stale = clone / ".git" / "packed-refs.lock"
    stale.write_text("x")
    source = _source(git_origin.url)
    key = f"survivor-{uuid.uuid4().hex}"
    released_keys.append(key)

    async def _op(on_gone):
        await cli_fetch(
            clone, "origin", source, prune=False, timeout=60, on_gone=on_gone
        )

    async def main():
        task = asyncio.ensure_future(run_git_cli_op(_op, timeout=60, busy_key=key))
        await _until(lambda: started.exists() and git_groups)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert git_op_in_flight(key)
        assert stale.exists()
        with pytest.raises(GitCliBusyError):
            await cli_fetch(clone, "origin", source, prune=False, timeout=60)
        release.touch()
        await _until(lambda: not git_op_in_flight(key))
        assert not stale.exists()

    try:
        _run(loop, main)
    finally:
        release.touch()


@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="needs /proc to be quick")
@_LOOPS
def test_a_cancel_while_git_is_being_started_still_ends_its_group(
    loop, git_origin, tmp_path, blackhole, monkeypatch, processes_with, git_groups
):
    """Cancelled while create_subprocess_exec still sets up sh's pipes, with
    git already running, the event loop kills sh only, and the op has no group
    to stop.

    The watchdog in sh's group kills the rest as sh's stdin closes, and
    the op is over (on_gone, the clone cleaned up) only once nothing
    holds the clone's lock any more: no process of it is left by then.

    The cancel is made to land there: a callback queued before the
    loop's own for the new process holds the loop until git runs, then
    cancels the op.
    """
    pytest.importorskip(loop)
    marker = f"spawn-{uuid.uuid4().hex}"
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, f"http://127.0.0.1:{blackhole}/{marker}.git")
    spawn = asyncio.create_subprocess_exec
    ops = []
    left_at_gone = []

    def _git_runs() -> bool:
        return any(
            not args.startswith(git_cli._SH) for _, _, args in processes_with(marker)
        )

    def _cancel_once_git_runs() -> None:
        _wait_until(_git_runs)
        ops[0].cancel()

    async def _cancelled_mid_start(*args, **kwargs):
        asyncio.get_running_loop().call_soon(_cancel_once_git_runs)
        return await spawn(*args, **kwargs)

    monkeypatch.setattr(git_cli.asyncio, "create_subprocess_exec", _cancelled_mid_start)

    def _gone(succeeded):
        left_at_gone.append(processes_with(marker))

    async def main():
        ops.append(
            asyncio.ensure_future(
                cli_fetch(
                    clone,
                    "origin",
                    _source(git_origin.url),
                    prune=False,
                    timeout=60,
                    on_gone=_gone,
                )
            )
        )
        done, _ = await asyncio.wait(ops, timeout=10)
        assert done and ops[0].cancelled()
        # The start was given up on (no group was made): the op finishes on a
        # task of its own.
        assert git_groups == []
        assert git_cli.background_ops() == 1
        await _until(lambda: left_at_gone)

    _run(loop, main)

    assert left_at_gone == [[]]
    assert clone_lock_path(clone).read_bytes() == b""


def _open_pipes_and_files() -> set:
    """This process's open pipes and files, as (fd, device, inode).

    Sockets are left out, as in-process clients (metrics) open and close
    theirs at any time. Compare with ``<=``: other tests' objects may
    close fds of theirs meanwhile.
    """
    found = set()
    for name in os.listdir("/dev/fd"):
        try:
            st = os.fstat(int(name))
        except OSError as e:
            if e.errno != errno.EBADF:
                raise
            continue  # closed since the listing: the listing's own
        if stat.S_ISFIFO(st.st_mode) or stat.S_ISREG(st.st_mode):
            found.add((int(name), st.st_dev, st.st_ino))
    return found


async def _cancelled_within(
    task: "asyncio.Future", seconds: float, then: Optional[asyncio.Event] = None
) -> None:
    """Cancel ``task`` and wait up to ``seconds`` for it to end, cancelled: an
    op that never ends fails the test rather than hang it (the event loop's end
    then cancels it again).

    ``then`` is set once the cancel is requested, before the task has
    run again.
    """
    task.cancel()
    if then is not None:
        then.set()
    done, _ = await asyncio.wait({task}, timeout=seconds)
    assert done, f"the op was still running {seconds}s after its cancel"
    assert task.cancelled()


def test_a_cancel_before_asyncio_has_connected_sh_s_pipes_ends_the_group(
    git_origin, tmp_path, blackhole, monkeypatch, processes_with
):
    """The asyncio loop, giving up on a start it was cancelled in, kills sh and
    closes the pipes it has connected, then waits for sh, and for the rest of
    its pipes too, which it goes on connecting, and which git holds while it
    lives.

    sh's pipes are the op's own, which asyncio does not wait for, so the
    cancel ends the group at once however far asyncio got. Here the
    cancel comes before asyncio has connected any.
    """
    real = asyncio.base_subprocess.BaseSubprocessTransport._connect_pipes
    connect = asyncio.Event()

    async def _late(self, waiter):
        await connect.wait()
        await real(self, waiter)

    monkeypatch.setattr(
        asyncio.base_subprocess.BaseSubprocessTransport, "_connect_pipes", _late
    )
    marker = f"unconnected-{uuid.uuid4().hex}"
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, f"http://127.0.0.1:{blackhole}/{marker}.git")
    gone = []

    async def main():
        task = asyncio.ensure_future(
            cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=gone.append,
            )
        )
        await _until(lambda: processes_with(marker))
        await _cancelled_within(task, 10, then=connect)
        await _until(lambda: gone)

    fds = _open_pipes_and_files()
    _run("asyncio", main)

    assert gone == [False]
    assert processes_with(marker) == []
    assert clone_lock_path(clone).read_bytes() == b""
    assert _open_pipes_and_files() <= fds  # sh's pipes and the lock's: all closed


class _SetBlockingFails:
    """git_cli's ``os``, whose ``set_blocking`` fails on its ``nth`` call."""

    def __init__(self, nth: int) -> None:
        self._nth = nth
        self._calls = 0

    def __getattr__(self, name: str):
        return getattr(os, name)

    def set_blocking(self, fd: int, blocking: bool) -> None:
        self._calls += 1
        if self._calls == self._nth:
            raise OSError(errno.ENOMEM, "set_blocking failed")
        os.set_blocking(fd, blocking)


@pytest.mark.parametrize("reader", ["status", "stderr"])
def test_a_start_that_cannot_read_sh_s_pipes_runs_nothing_and_leaves_nothing(
    git_origin, tmp_path, blackhole, monkeypatch, processes_with, reader
):
    """Reading sh's pipes is set up before sh starts, so a failure there (an
    add_reader that fails, as epoll_ctl can) runs no sh: every pipe is closed,
    and the clone released."""
    monkeypatch.setattr(
        git_cli, "os", _SetBlockingFails(1 if reader == "status" else 2)
    )
    marker = f"unread-{uuid.uuid4().hex}"
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, f"http://127.0.0.1:{blackhole}/{marker}.git")
    gone = []

    async def main():
        with pytest.raises(GitCliLocalError, match="set_blocking failed"):
            await cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=gone.append,
            )
        await _until(lambda: gone)

    fds = _open_pipes_and_files()
    _run("asyncio", main)

    assert gone == [False]
    assert processes_with(marker) == []
    assert clone_lock_path(clone).read_bytes() == b""
    assert _open_pipes_and_files() <= fds  # sh's pipes and the lock's: all closed


class _StderrCloseFails:
    """git_cli's ``os``, whose ``close`` of the read end of the third pipe it
    makes (sh's stderr) closes it, then raises."""

    def __init__(self) -> None:
        self._pipes = 0
        self._stderr = -1

    def __getattr__(self, name: str):
        return getattr(os, name)

    def pipe(self):
        read, write = os.pipe()
        self._pipes += 1
        if self._pipes == 3:
            self._stderr = read
        return read, write

    def close(self, fd: int) -> None:
        os.close(fd)
        if fd == self._stderr:
            self._stderr = -1
            raise OSError(errno.EIO, "close failed")


def test_a_pipe_whose_close_fails_still_lets_the_op_end(
    git_origin, tmp_path, monkeypatch
):
    """The reader of one of sh's pipes says it is done whatever its close
    raises, so the op's wait for sh's pipes ends all the same."""
    monkeypatch.setattr(git_cli, "os", _StderrCloseFails())
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, git_origin.url)
    gone = []

    async def main():
        await asyncio.wait_for(
            cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=gone.append,
            ),
            30,  # long before the op's own 60 s timeout
        )

    _run("asyncio", main)

    assert gone == [True]


@pytest.mark.parametrize("cancelled", ["starting", "running"])
def test_an_op_the_loop_s_end_overtakes_is_still_finished(
    git_origin, tmp_path, blackhole, monkeypatch, processes_with, git_groups, cancelled
):
    """asyncio.run shuts the loop's executor down before it closes the loop,
    while what its end set going may still run: the stop of an op it
    cancelled, or the clean-up after a start it cancelled. The op's files are
    then seen to on the loop's own thread, and the op is finished."""
    connect = asyncio.Event()
    if cancelled == "starting":
        real = asyncio.base_subprocess.BaseSubprocessTransport._connect_pipes

        async def _late(self, waiter):
            await connect.wait()
            await real(self, waiter)

        monkeypatch.setattr(
            asyncio.base_subprocess.BaseSubprocessTransport, "_connect_pipes", _late
        )
    marker = f"overtaken-{uuid.uuid4().hex}"
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, f"http://127.0.0.1:{blackhole}/{marker}.git")
    gone = []

    async def main():
        task = asyncio.ensure_future(
            cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=gone.append,
            )
        )
        await _until(
            lambda: processes_with(marker) and (cancelled == "starting" or git_groups)
        )
        await asyncio.get_running_loop().shutdown_default_executor()
        await _cancelled_within(task, 10, then=connect)
        await _until(lambda: gone)

    fds = _open_pipes_and_files()
    _run("asyncio", main)

    assert gone == [False]
    assert processes_with(marker) == []
    assert clone_lock_path(clone).read_bytes() == b""
    assert _open_pipes_and_files() <= fds  # sh's pipes and the lock's: all closed


@pytest.mark.parametrize("ending", ["cancel", "OSError"])
@_LOOPS
def test_a_start_given_up_on_leaves_the_clone_held_until_its_last_process_exits(
    loop, ending, git_origin, tmp_path, monkeypatch, processes_with
):
    """The same, made certain: the event loop gives up on a start once git runs
    (cancelled, or failing as it connects sh's pipes), with a process of git's
    that left the group (beyond the watchdog's reach) holding the clone's lock,
    which on_gone waits for."""
    pytest.importorskip(loop)
    marker = f"escaped-{uuid.uuid4().hex}"
    shims = tmp_path / "bin"
    shims.mkdir()
    started = shims / "escaped.started"
    (shims / "git").write_text(
        "#!/bin/sh\n"
        f'"{sys.executable}" -c "import os, sys, time; os.setsid(); '
        f"open(sys.argv[1], 'w').close(); time.sleep(1.5)\" '{started}' {marker} &\n"
        "exec sleep 30\n"
    )
    (shims / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, git_origin.url)
    spawn = asyncio.create_subprocess_exec

    async def _given_up_on(*args, **kwargs):
        proc = await spawn(*args, **kwargs)
        await _until(started.exists)
        # What the event loop does as it gives up on a start: kill sh, close
        # the pipes it had connected, raise the cancel.
        proc.kill()
        await proc.wait()
        proc._transport.close()  # type: ignore[attr-defined]  # as git_cli does
        if ending == "OSError":
            raise OSError(24, "Too many open files")
        raise asyncio.CancelledError

    monkeypatch.setattr(git_cli.asyncio, "create_subprocess_exec", _given_up_on)
    seen_at_gone = []

    def _gone(succeeded):
        seen_at_gone.append((processes_with(marker), _lock_is_free(clone)))

    async def main():
        expected = asyncio.CancelledError if ending == "cancel" else GitCliLocalError
        with pytest.raises(expected):
            await cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=_gone,
            )
        assert seen_at_gone == []
        await _until(lambda: seen_at_gone)

    _run(loop, main)

    assert seen_at_gone == [([], True)]
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.parametrize("stuck", [False, True], ids=["removable", "stuck"])
@pytest.mark.asyncio
async def test_a_given_up_start_cleans_up_after_an_op_that_held_the_clone_meanwhile(
    stuck, git_origin, tmp_path, monkeypatch
):
    """A start given up on waits for the clone's lock with no fd of its own on
    it, so another process can hold the clone first, record its op, start a
    clone beside it and die.

    Once the start has the lock, what that op left goes too; when some
    of it cannot, its record stays, for the next op to try again.
    """
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, git_origin.url)
    lock = clone_lock_path(clone)
    partial = clone.parent / f".{clone.name}.clone-0123456789abcdef"
    shims = tmp_path / "bin"
    shims.mkdir()
    started = shims / "other.started"
    # Holds the clone's lock from git's start (it inherits git's fd) until it
    # exits, out of the group's reach: the other process's op, recorded with
    # a pid no process has, which dies with a clone half made.
    other = shims / "other.py"
    other.write_text(
        textwrap.dedent(
            """\
            import os, sys
            os.setsid()
            lock, partial, started = sys.argv[1:]
            with open(lock, "r+b") as f:
                f.write(b"4194303\\n")
                f.truncate()
            os.makedirs(os.path.join(partial, ".git"))
            open(started, "w").close()
            """
        )
    )
    (shims / "git").write_text(
        "#!/bin/sh\n"
        f"\"{sys.executable}\" '{other}' '{lock}' '{partial}' '{started}' &\n"
        "exec sleep 30\n"
    )
    (shims / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    if stuck:
        rmtree = shutil.rmtree

        def _busy(path, *args, **kwargs):
            if Path(path) == partial:
                raise OSError(errno.EBUSY, "Device or resource busy", str(path))
            rmtree(path, *args, **kwargs)

        monkeypatch.setattr(git_cli.shutil, "rmtree", _busy)
    spawn = asyncio.create_subprocess_exec

    async def _given_up_on(*args, **kwargs):
        proc = await spawn(*args, **kwargs)
        await _until(started.exists)
        proc.kill()
        await proc.wait()
        proc._transport.close()  # type: ignore[attr-defined]  # as git_cli does
        raise OSError(24, "Too many open files")

    monkeypatch.setattr(git_cli.asyncio, "create_subprocess_exec", _given_up_on)
    gone = []

    with pytest.raises(GitCliLocalError):
        await cli_fetch(
            clone,
            "origin",
            _source(git_origin.url),
            prune=False,
            timeout=60,
            on_gone=gone.append,
        )
    await _until(lambda: gone)

    assert gone == [False]
    assert partial.exists() is stuck
    assert lock.read_bytes() == (b"4194303\n" if stuck else b"")


@pytest.mark.parametrize(
    "error",
    [OSError(errno.EMFILE, "Too many open files"), RuntimeError("lock broke")],
    ids=["EMFILE", "other"],
)
@pytest.mark.asyncio
async def test_a_given_up_start_whose_lock_cannot_be_taken_again_still_ends(
    error, git_origin, tmp_path, monkeypatch
):
    """The clean-up after a start given up on is the only thing left that ends
    the op.

    When it cannot take the clone's lock again (EMFILE comes in
    clusters, so the spawn's failure is likely to be followed by the
    lock's; or anything else goes wrong there), the op still ends:
    on_gone is told it failed, no fd is left, and the op stays recorded
    in the lock file for the next op on the clone to clean up after.
    """
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, git_origin.url)

    def _lock_fails(repo_path):
        raise error

    async def _given_up_on(*args, **kwargs):
        monkeypatch.setattr(git_cli, "take_clone_lock", _lock_fails)
        raise OSError(errno.EMFILE, "Too many open files")

    monkeypatch.setattr(git_cli.asyncio, "create_subprocess_exec", _given_up_on)
    gone = []
    errors = []
    sink = opal_common_logger.logger.add(
        lambda m: errors.append(m.record["message"]), level="ERROR"
    )
    try:
        with pytest.raises(GitCliLocalError):
            await cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=gone.append,
            )
        await _until(lambda: gone)
        await _until(lambda: git_cli.background_ops() == 0)
    finally:
        opal_common_logger.logger.remove(sink)

    assert gone == [False]
    assert git_cli._lock_fds == {}
    assert clone_lock_path(clone).read_text() == f"{os.getpid()}\n"
    assert [m for m in errors if "Could not lock" in m and repr(error) in m]


@pytest.mark.parametrize("ending", ["success", "failure", "timeout"])
@pytest.mark.asyncio
async def test_an_on_gone_that_raises_still_lets_the_op_release_its_clone(
    ending, git_origin, tmp_path, blackhole
):
    """What on_gone raises is logged; the op still releases its clone's lock
    and clears its record."""
    clone = tmp_path / "cli"
    url = git_origin.url
    if ending == "failure":
        url = str(tmp_path / "missing.git")
    elif ending == "timeout":
        url = f"http://127.0.0.1:{blackhole}/hung.git"
    _clone_at(clone, git_origin.url, url)
    calls = []

    def _gone(succeeded):
        calls.append(succeeded)
        raise RuntimeError("on_gone broke")

    errors = []
    sink = opal_common_logger.logger.add(
        lambda m: errors.append(m.record["message"]), level="ERROR"
    )
    try:
        fetch = cli_fetch(
            clone,
            "origin",
            _source(url),
            prune=False,
            timeout=0.5 if ending == "timeout" else 60,
            on_gone=_gone,
        )
        if ending == "success":
            await fetch
        else:
            with pytest.raises((GitCliError, GitCliTimeoutError)):
                await fetch
        await _until(lambda: calls)
        await _until(lambda: git_cli.background_ops() == 0)
    finally:
        opal_common_logger.logger.remove(sink)

    assert calls == [ending == "success"]
    logged = f"on_gone of git fetch of {clone} raised: RuntimeError('on_gone broke')"
    assert logged in errors
    assert _lock_is_free(clone)
    assert clone_lock_path(clone).read_bytes() == b""


@_LOOPS
def test_the_event_loop_ending_mid_stop_kills_git_and_leaves_the_clone_to_the_next_op(
    loop, git_origin, tmp_path, monkeypatch, processes_with, released_keys, git_groups
):
    """asyncio.run (and uvicorn) cancel every task left as the loop ends,
    the stop of a cancelled op included: git gets SIGKILL there and then,
    not once its SIGTERM grace is over. Nothing says the group is gone, so
    its clone is not cleaned up: the op stays recorded in the clone's lock,
    and the next op on the clone cleans it up. It leaves flight (on_gone is
    told None), so the preload's drain does not wait for it."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 30.0)
    started = _ssh_shim(
        tmp_path, monkeypatch, _ignore_sigterm(tmp_path / "bin" / "ssh.started")
    )
    marker = f"loopend-{uuid.uuid4().hex}"
    cancelled_at = []
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, f"ssh://git@127.0.0.1:1/{marker}.git")
    stale = clone / ".git" / "packed-refs.lock"
    stale.write_text("x")
    key = f"loopend-{marker}"
    released_keys.append(key)

    async def main():
        task = asyncio.ensure_future(
            run_git_cli_op(
                partial(
                    cli_fetch,
                    clone,
                    "origin",
                    _source(git_origin.url),
                    prune=False,
                    timeout=60,
                ),
                timeout=60,
                busy_key=key,
            )
        )
        await _until(lambda: started.exists() and git_groups)
        task.cancel()
        cancelled_at.append(time.monotonic())
        await asyncio.sleep(0.3)

    fds = _open_pipes_and_files()
    _run(loop, main)
    _wait_until(lambda: processes_with(marker) == [])

    # Well inside the 30 s grace: the loop's end cut it short.
    assert time.monotonic() - cancelled_at[0] < 15
    if loop == "asyncio":  # uvloop keeps pipes of its own past its close
        assert _open_pipes_and_files() <= fds  # sh's pipes and the lock's: all closed
    assert not git_op_in_flight(key)
    assert drain_git_ops(0) is True
    assert stale.exists()
    assert clone_lock_path(clone).read_text().strip() == str(os.getpid())
    _point_at(clone, git_origin.url)
    _run(
        loop,
        lambda: cli_fetch(
            clone, "origin", _source(git_origin.url), prune=False, timeout=60
        ),
    )
    assert not stale.exists()


def test_the_event_loop_ending_mid_stop_keeps_the_op_s_hung_marker(
    git_origin, tmp_path, monkeypatch, processes_with, released_keys
):
    """An op past its timeout has written its hung-op marker.

    The loop ending while it is stopped says nothing of whether its git
    ever ended, so the marker stays, as a libgit2 op's does while its
    thread runs on.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 30.0)
    started = _ssh_shim(
        tmp_path, monkeypatch, _ignore_sigterm(tmp_path / "bin" / "ssh.started")
    )
    marker = f"hungmark-{uuid.uuid4().hex}"
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, f"ssh://git@127.0.0.1:1/{marker}.git")
    markers = tmp_path / "markers"
    markers.mkdir()
    key = f"hungmark-{marker}"
    released_keys.append(key)
    # Stopped before git reaches ssh, git ends at once, and the loop's end
    # has no stop to cut short.
    timeout = _SHIM_TIMEOUT

    async def main():
        asyncio.ensure_future(
            run_git_cli_op(
                partial(
                    cli_fetch,
                    clone,
                    "origin",
                    _source(git_origin.url),
                    prune=False,
                    timeout=timeout,
                ),
                timeout=timeout,
                busy_key=key,
                marker_dir=markers,
                mark_when_hung=True,
            )
        )
        await _until(started.exists)
        assert list(markers.iterdir()) == [], "git reached ssh only after its timeout"
        await _until(lambda: list(markers.iterdir()), timeout=timeout + _READY_SECONDS)
        await asyncio.sleep(0.1)  # inside the 30 s SIGTERM grace

    _run("asyncio", main)
    _wait_until(lambda: processes_with(marker) == [])

    assert not git_op_in_flight(key)
    assert list(markers.iterdir()) != []


@_LOOPS
def test_the_event_loop_ending_while_a_member_outlives_sigkill_leaves_it_the_clone(
    loop, git_origin, tmp_path, monkeypatch, released_keys
):
    """The preload's shape: a timeout whose group outlives SIGKILL, then
    asyncio.run ends.

    The op leaves flight, but the survivor keeps the clone (a next op is
    busy) until it exits; then the next op cleans up. The survivor holds
    sh's stderr, so it is the loop's end that closes this process's ends
    of sh's pipes, and its lock.
    """
    release = tmp_path / "release"
    started = _ssh_shim(
        tmp_path,
        monkeypatch,
        _out_of_reach(tmp_path / "bin" / "ssh.started", release),
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 0.3)
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, "ssh://git@127.0.0.1:1/survivor.git")
    stale = clone / ".git" / "packed-refs.lock"
    stale.write_text("x")
    source = _source(git_origin.url)
    key = f"preload-{uuid.uuid4().hex}"
    released_keys.append(key)

    async def main():
        with pytest.raises(GitCliTimeoutError):
            await run_git_cli_op(
                partial(
                    cli_fetch,
                    clone,
                    "origin",
                    source,
                    prune=False,
                    timeout=_SHIM_TIMEOUT,
                ),
                timeout=_SHIM_TIMEOUT,
                busy_key=key,
            )
        assert started.exists(), "git was stopped before its ssh left the group"

    fds = _open_pipes_and_files()
    try:
        _run(loop, main)

        if loop == "asyncio":  # uvloop keeps pipes of its own past its close
            assert _open_pipes_and_files() <= fds  # sh's pipes and the lock's: closed
        assert not git_op_in_flight(key)
        assert drain_git_ops(0) is True
        with pytest.raises(GitCliBusyError):
            _run(
                loop,
                lambda: cli_fetch(clone, "origin", source, prune=False, timeout=60),
            )
        assert stale.exists()
    finally:
        release.touch()
    _wait_until(lambda: _lock_is_free(clone))
    _point_at(clone, git_origin.url)
    _run(loop, lambda: cli_fetch(clone, "origin", source, prune=False, timeout=60))
    assert not stale.exists()


# --- the pre-fork sweep -----------------------------------------------------------


def _dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def test_the_pre_fork_sweep_removes_what_dead_ops_left_and_skips_held_clones(
    git_origin, tmp_path, monkeypatch, orphan
):
    shm = tmp_path / "shm"
    shm.mkdir()
    monkeypatch.setattr(git_cli, "_SHM", str(shm))
    disk = tmp_path / "tmp"
    disk.mkdir()
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(disk))
    clones = tmp_path / "git_sources"
    free, held = clones / "free", clones / "held"
    for clone in (free, held):
        _clone_at(clone, git_origin.url, git_origin.url)
    free_left = _plant_leftovers(free) + [clones / ".free.clone-0123456789abcdef"]
    held_left = _plant_leftovers(held) + [clones / ".held.clone-0123456789abcdef"]
    for directory in (free_left[-1], held_left[-1]):
        directory.mkdir()
    gone_clone = clones / ".deleted.clone-fedcba9876543210"
    (gone_clone / ".git").mkdir(parents=True)
    hung_markers = clones / "free.hung"
    hung_markers.mkdir()
    dead_keys = [d / f"opal-git-ssh-{_dead_pid()}-x1" for d in (shm, disk)]
    other = [shm / "opal-git-ssh-x3", shm / "something-else"]
    for directory in (*dead_keys, *other):
        directory.mkdir()
        (directory / "id").write_text("key")
    live_key, live_lock = git_cli._make_key_dir()
    orphan(held)

    try:
        sweep_clone_leftovers(clones)
    finally:
        os.close(live_lock)

    assert [p for p in free_left if p.exists()] == []
    assert not gone_clone.exists()
    assert [p for p in held_left if not p.exists()] == []
    assert hung_markers.exists()
    assert [d for d in dead_keys if d.exists()] == []
    assert all(Path(d).exists() for d in (live_key, *other))
    assert "refs/remotes/origin/master" in _refs(free)


def test_the_pre_fork_sweep_of_no_clones_at_all_does_nothing(tmp_path):
    sweep_clone_leftovers(tmp_path / "none")


@pytest.mark.parametrize("stuck", [True, False], ids=["stuck", "removable"])
def test_the_pre_fork_sweep_clears_a_dead_op_s_record_once_all_it_left_is_gone(
    stuck, git_origin, tmp_path
):
    """A leftover the sweep cannot remove (a directory where packed-refs.new
    would be) keeps the dead op recorded, for the next op on the clone to try
    again; the rest of what it left goes either way."""
    clones = tmp_path / "git_sources"
    clone = clones / "src"
    _clone_at(clone, git_origin.url, git_origin.url)
    lock = clone / ".git" / "packed-refs.lock"
    lock.write_text("")
    new_packed_refs = clone / ".git" / "packed-refs.new"
    if stuck:
        (new_packed_refs / "x").mkdir(parents=True)
    else:
        new_packed_refs.write_text("")
    clone_lock_path(clone).write_text("4194303\n")

    sweep_clone_leftovers(clones)

    assert not lock.exists()
    assert new_packed_refs.exists() is stuck
    assert (clone_lock_path(clone).read_bytes() != b"") is stuck


@pytest.mark.parametrize("by", ["pre-fork sweep", "dead op's clean-up"])
def test_a_fetch_keep_goes_under_the_clone_s_lock_whatever_pid_and_host_it_names(
    by, git_origin, tmp_path
):
    """Only a git command-line fetch writes a fetch's .keep, and it holds the
    clone's lock for as long as any of its processes lives: under that lock,
    the .keep is a dead fetch's, whatever pid (a restart in the same pod hands
    the old ones out again, this one's included) or host (a volume of clones
    mounted by a new pod) it names.

    Left, the pack it keeps would never be merged, and every repack of
    the clone would end with two packs. A .keep that is not a fetch's
    stays.
    """
    clones = tmp_path / "git_sources"
    clone = clones / "src"
    _clone_at(clone, git_origin.url, git_origin.url)
    for _ in range(2):
        git_origin.commit("master")
        # Without --no-auto-maintenance, git 2.56's fetch starts a detached
        # `git maintenance run --auto`, whose repack of these packs races
        # the one below.
        subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "-c",
                "fetch.unpackLimit=1",
                "fetch",
                "--no-auto-maintenance",
                "-q",
            ],
            check=True,
        )
    pack_dir = clone / ".git" / "objects" / "pack"
    packs = sorted(pack_dir.glob("pack-*.pack"))
    assert len(packs) >= 2
    host = socket.gethostname()
    fetch_keeps = [p.with_suffix(".keep") for p in packs[:2]]
    fetch_keeps[0].write_text(f"fetch-pack {os.getpid()} on {host}\n")
    fetch_keeps[1].write_text(f"fetch-pack 4242 on not-{host}\n")
    kept = pack_dir / "pack-3333.keep"
    kept.write_text("keep this one\n")

    if by == "pre-fork sweep":
        sweep_clone_leftovers(clones)
    else:
        clone_lock_path(clone).write_text("4194303\n")
        git_cli.clean_up_unfinished_op(clone)

    assert [k for k in fetch_keeps if k.exists()] == []
    assert kept.exists()
    assert clone_lock_path(clone).read_bytes() == b""
    git_fetcher_module._repack_clone(clone, timeout=60)
    assert git_fetcher_module._count_pack_files(clone) == 1


def test_the_sweep_removes_a_key_dir_no_process_holds_whatever_pid_it_names(
    tmp_path, monkeypatch
):
    """After a restart in the same pod, /dev/shm is still there and the new
    container's processes have the old ones' pids, this one's included: the key
    directory of a process that died goes even when the pid in its name is a
    live process's now."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    left = [tmp_path / f"opal-git-ssh-{pid}-x1" for pid in (os.getpid(), 1)]
    for directory in left:
        directory.mkdir()
        (directory / "id").write_text("key")

    git_cli.remove_dead_key_dirs()

    assert [d for d in left if d.exists()] == []


def test_the_sweep_leaves_the_key_dir_of_an_op_under_way(tmp_path, monkeypatch):
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    url = "ssh://git@127.0.0.1:22/repo.git"
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=SSHAuthData(username="git", private_key="key"),
    )

    with git_cli._git_env(
        source, git_cli._remote_for_git(url, source), tmp_path / "clone"
    ) as (env, _):
        ssh = shlex.split(env["GIT_SSH_COMMAND"])
        key = Path(ssh[ssh.index("-i") + 1])
        git_cli.remove_dead_key_dirs()
        assert key.read_text() == "key\n"

    assert not key.parent.exists()


def test_a_sweep_between_an_op_s_mkdtemp_and_its_lock_leaves_the_key_dir(
    tmp_path, monkeypatch
):
    """A worker that starts while another one's SSH op has made its key
    directory and not yet locked it: the starting worker's sweep must not take
    the lock first and remove the directory, which would fail the op."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    url = "ssh://git@127.0.0.1:22/repo.git"
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=SSHAuthData(username="git", private_key="key"),
    )
    lock = git_cli._lock_key_dir
    swept = []

    def _swept_first(path):
        if not swept:
            swept.append(path)
            git_cli.remove_dead_key_dirs()
        return lock(path)

    monkeypatch.setattr(git_cli, "_lock_key_dir", _swept_first)

    with git_cli._git_env(
        source, git_cli._remote_for_git(url, source), tmp_path / "clone"
    ) as (env, _):
        ssh = shlex.split(env["GIT_SSH_COMMAND"])
        key = Path(ssh[ssh.index("-i") + 1])
        assert key.read_text() == "key\n"

    assert len(swept) == 1
    assert not key.parent.exists()


def test_the_sweep_removes_a_key_dir_with_no_key_once_it_is_old_enough(
    tmp_path, monkeypatch
):
    """A key directory with no key in it, whose lock no process holds: one that
    is new may be an op's that has not locked it yet, and stays; one older than
    any op takes to lock it was a dead process's, and goes."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    new, old = (tmp_path / f"opal-git-ssh-{_dead_pid()}-{n}" for n in ("x1", "x2"))
    new.mkdir()
    old.mkdir()
    made = time.time() - git_cli._KEY_DIR_SETUP_SECONDS - 1
    os.utime(old, (made, made))

    git_cli.remove_dead_key_dirs()

    assert new.exists()
    assert not old.exists()


def test_a_key_dir_with_no_key_is_left_alone_for_one_minute(tmp_path, monkeypatch):
    """The setup grace is one minute: a key directory with no key and no
    held lock stays at just under a minute old and goes at just over it."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    now = time.time()
    monkeypatch.setattr(git_cli.time, "time", lambda: now)
    young, aged = (tmp_path / f"opal-git-ssh-{_dead_pid()}-{n}" for n in ("y1", "a1"))
    young.mkdir()
    aged.mkdir()
    os.utime(young, (now - 59.5, now - 59.5))
    os.utime(aged, (now - 60.5, now - 60.5))

    git_cli.remove_dead_key_dirs()

    assert young.exists()
    assert not aged.exists()


def test_a_key_dir_with_no_key_goes_once_it_is_a_minute_old(tmp_path, monkeypatch):
    """The setup grace ends at one minute: a key directory with no key and no
    held lock that is a minute old to the second goes."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    made = int(time.time()) - 3600
    monkeypatch.setattr(git_cli.time, "time", lambda: made + 60.0)
    aged = tmp_path / f"opal-git-ssh-{_dead_pid()}-m1"
    aged.mkdir()
    os.utime(aged, (made, made))
    assert os.lstat(aged).st_mtime == made

    git_cli.remove_dead_key_dirs()

    assert not aged.exists()


def test_a_key_dir_made_while_the_clock_read_the_epoch_goes(tmp_path, monkeypatch):
    """A key directory made while the clock still read the epoch (a host with
    no clock battery, before NTP set it) is long past the setup grace once the
    clock is right: with no key and no held lock, it goes."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    dirs = [tmp_path / f"opal-git-ssh-{_dead_pid()}-e{made}" for made in (0, 1)]
    for made, path in enumerate(dirs):
        path.mkdir()
        os.utime(path, (made, made))

    git_cli.remove_dead_key_dirs()

    assert [path.exists() for path in dirs] == [False, False]


def test_a_key_dir_whose_age_cannot_be_read_is_judged_by_its_lock(
    tmp_path, monkeypatch
):
    """A new key directory with no key, whose age the sweep cannot read (it
    went meanwhile, or the lstat fails): it is not taken for one being set up,
    so its lock decides, and a dead process's directory goes."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    new = tmp_path / f"opal-git-ssh-{_dead_pid()}-x1"
    new.mkdir()
    real_lstat = os.lstat
    failed = []

    def _lstat_fails_once(path, *args, **kwargs):
        if os.fspath(path) == os.fspath(new) and not failed:
            failed.append(path)
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(git_cli.os, "lstat", _lstat_fails_once)

    git_cli.remove_dead_key_dirs()

    assert failed
    assert not new.exists()


def test_a_key_dir_the_sweep_cannot_lock_is_logged_and_left(tmp_path, monkeypatch):
    """Where the filesystem refuses an flock (ENOLCK), the sweep cannot tell
    whether a live process uses a key directory: it leaves it, and says so."""
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path))
    monkeypatch.setattr(git_cli.tempfile, "tempdir", str(tmp_path))
    left = tmp_path / f"opal-git-ssh-{_dead_pid()}-x1"
    left.mkdir()
    (left / "id").write_text("key")
    _flock_fails_with(monkeypatch, errno.ENOLCK)
    warnings = []
    sink = opal_common_logger.logger.add(
        lambda m: warnings.append(m.record["message"]), level="WARNING"
    )
    try:
        git_cli.remove_dead_key_dirs()
    finally:
        opal_common_logger.logger.remove(sink)

    assert (left / "id").exists()
    assert [m for m in warnings if str(left) in m and "leaving it" in m]


# --- the clean-up a libgit2 fetch runs first ------------------------------------


@pytest.mark.parametrize("stuck", [True, False], ids=["stuck", "removable"])
def test_unfinished_op_clean_up_keeps_the_record_until_all_it_left_is_gone(
    stuck, git_origin, tmp_path
):
    """What a dead op left that cannot be removed (a directory where packed-
    refs.new would be) keeps it recorded, for the next op on the clone to try
    again; the rest goes either way."""
    clone = tmp_path / "git_sources" / "src"
    _clone_at(clone, git_origin.url, git_origin.url)
    lock = clone / ".git" / "packed-refs.lock"
    lock.write_text("")
    new_packed_refs = clone / ".git" / "packed-refs.new"
    if stuck:
        (new_packed_refs / "x").mkdir(parents=True)
    else:
        new_packed_refs.write_text("")
    clone_lock_path(clone).write_text("4194303\n")

    git_cli.clean_up_unfinished_op(clone)

    assert not lock.exists()
    assert new_packed_refs.exists() is stuck
    assert (clone_lock_path(clone).read_bytes() != b"") is stuck
    assert _lock_is_free(clone)


def test_unfinished_op_clean_up_leaves_a_clone_whose_lock_another_op_holds(
    git_origin, tmp_path
):
    """While an op holds the clone's lock (a git fetch of this process or
    another), the locks of its git are its own, however recorded: they stay,
    and the skip is logged at DEBUG.

    Once the op is gone with its record left behind, they were a dead
    op's: they go, and the record with them.
    """
    clone = tmp_path / "git_sources" / "src"
    _clone_at(clone, git_origin.url, git_origin.url)
    left = _plant_leftovers(clone)
    debug: list = []
    sink = opal_common_logger.logger.add(
        lambda m: debug.append(m.record["message"]), level="DEBUG"
    )
    holder = git_cli.take_clone_lock(clone)
    assert holder is not None
    try:
        git_cli.mark_op_started(holder)

        git_cli.clean_up_unfinished_op(clone)

        assert [p for p in left if not p.exists()] == []
        assert clone_lock_path(clone).read_text().strip() == str(os.getpid())
        assert [m for m in debug if "another op holds its lock" in m]
    finally:
        git_cli.drop_clone_lock(holder)
        opal_common_logger.logger.remove(sink)

    git_cli.clean_up_unfinished_op(clone)

    assert [p for p in left if p.exists()] == []
    assert clone_lock_path(clone).read_text() == ""


def test_unfinished_op_clean_up_with_no_op_recorded_removes_nothing(
    git_origin, tmp_path
):
    """No record, no dead op: a lock in the clone is someone's to finish (a
    libgit2 op takes no clone lock and writes no record), never this clean-up's
    to remove."""
    clone = tmp_path / "git_sources" / "src"
    _clone_at(clone, git_origin.url, git_origin.url)
    left = _plant_leftovers(clone)

    git_cli.clean_up_unfinished_op(clone)

    assert [p for p in left if not p.exists()] == []


@pytest.mark.parametrize("why", ["directory gone", "flock fails"])
def test_unfinished_op_clean_up_of_a_clone_it_cannot_lock_is_a_debug_line(
    why, git_origin, tmp_path, monkeypatch
):
    """A lock file that cannot be opened (its directory gone) or locked (on NFS
    without local_lock=flock, ENOLCK) fails every fetch's clean-up the same
    way, so it is logged at DEBUG only, no fd is left, and the fetch goes
    on."""
    if why == "directory gone":
        clone = tmp_path / "gone" / "src"
    else:
        clone = tmp_path / "git_sources" / "src"
        _clone_at(clone, git_origin.url, git_origin.url)
        _flock_fails_with(monkeypatch, errno.ENOLCK)
    debug: list = []
    sink = opal_common_logger.logger.add(
        lambda m: debug.append(m.record["message"]), level="DEBUG"
    )
    try:
        git_cli.clean_up_unfinished_op(clone)
    finally:
        opal_common_logger.logger.remove(sink)

    assert [m for m in debug if "Could not lock" in m and str(clone) in m]
    assert git_cli._lock_fds == {}


@pytest.mark.parametrize("recorded", [False, True], ids=["no-record", "record"])
def test_unfinished_op_clean_up_releases_the_clone_lock(git_origin, tmp_path, recorded):
    clone = tmp_path / "git_sources" / "src"
    _clone_at(clone, git_origin.url, git_origin.url)
    if recorded:
        fd = git_cli.take_clone_lock(clone)
        assert fd is not None
        git_cli.mark_op_started(fd)
        git_cli.drop_clone_lock(fd)

    git_cli.clean_up_unfinished_op(clone)

    assert _lock_is_free(clone)


@pytest.fixture
def preload(monkeypatch, preload_sandbox, no_redis):
    """preload_scopes with SCOPES on and the given sync_scopes, Redis and
    logging set up stubbed, as when_ready runs it in the gunicorn master."""

    def _preload(sync_scopes) -> None:
        class _Service:
            def __init__(self, *args, **kwargs):
                pass

            async def sync_scopes(self, **kwargs):
                await sync_scopes(**kwargs)

        monkeypatch.setattr(opal_common_logger, "_logs_configured", True)
        monkeypatch.setattr(task_module, "ScopesService", _Service)
        monkeypatch.setattr(opal_server_config, "SCOPES", True)
        task_module.ScopesPolicyWatcherTask.preload_scopes()

    return _preload


def test_the_preload_sweeps_before_its_sync_with_the_cli_fetch_off(
    git_origin, tmp_path, monkeypatch, preload
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    clone = GitPolicyFetcher.base_dir(tmp_path) / "0123abcd-0"
    _clone_at(clone, git_origin.url, git_origin.url)
    left = _plant_leftovers(clone)
    seen = []

    async def _sync(**kwargs):
        seen.append([p for p in left if p.exists()])

    preload(_sync)

    assert seen == [[]]


def test_the_preload_waits_for_ops_still_being_stopped_before_its_loop_ends(
    git_origin, tmp_path, monkeypatch, preload, processes_with, git_groups
):
    """A sync that leaves an op being stopped (a fetch cancelled twice, whose
    ssh sits out its SIGTERM grace): the preload's loop does not end, which
    would cut the stop short, until the op is over and its clone cleaned up."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 3.0)
    started = _ssh_shim(
        tmp_path, monkeypatch, _ignore_sigterm(tmp_path / "bin" / "ssh.started")
    )
    marker = f"preload-{uuid.uuid4().hex}"
    clone = GitPolicyFetcher.base_dir(tmp_path) / "0123abcd-0"
    _clone_at(clone, git_origin.url, f"ssh://git@127.0.0.1:1/{marker}.git")
    stale = clone / ".git" / "packed-refs.lock"

    async def _sync(**kwargs):
        task = asyncio.ensure_future(
            cli_fetch(clone, "origin", _source(git_origin.url), prune=False, timeout=60)
        )
        await _until(lambda: started.exists() and git_groups)
        stale.write_text("x")
        task.cancel()
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert git_cli.background_ops() == 1
        assert drain_git_ops(0) is False

    preload(_sync)

    assert processes_with(marker) == []
    assert not stale.exists()
    assert clone_lock_path(clone).read_bytes() == b""


def test_the_preload_waits_for_ops_being_stopped_no_longer_than_its_drain_timeout(
    git_origin, tmp_path, monkeypatch, preload, processes_with, git_groups
):
    """The same with a kill grace longer than SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT:
    the preload, which holds up the gunicorn master, waits for the drain
    timeout, not the grace, and warns. Its loop's end then SIGKILLs the op's
    group, and the op stays recorded in the clone's lock file, for the next
    op on the clone to clean up after."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 30.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT", 1.0)
    started = _ssh_shim(
        tmp_path, monkeypatch, _ignore_sigterm(tmp_path / "bin" / "ssh.started")
    )
    marker = f"preload-{uuid.uuid4().hex}"
    clone = GitPolicyFetcher.base_dir(tmp_path) / "0123abcd-0"
    _clone_at(clone, git_origin.url, f"ssh://git@127.0.0.1:1/{marker}.git")

    async def _sync(**kwargs):
        task = asyncio.ensure_future(
            cli_fetch(clone, "origin", _source(git_origin.url), prune=False, timeout=60)
        )
        await _until(lambda: started.exists() and git_groups)
        task.cancel()
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert git_cli.background_ops() == 1

    records = []
    sink = opal_common_logger.logger.add(
        lambda m: records.append(m.record), level="WARNING"
    )
    begun = time.monotonic()
    try:
        preload(_sync)
    finally:
        opal_common_logger.logger.remove(sink)
    took = time.monotonic() - begun

    assert took < 15, took
    assert any("still being stopped after 1.0s" in r["message"] for r in records)
    deadline = time.monotonic() + 10
    while processes_with(marker):
        assert time.monotonic() < deadline, processes_with(marker)
        time.sleep(0.05)
    assert clone_lock_path(clone).read_bytes() != b""


def test_the_preload_drops_asyncio_s_warning_about_children_reaped_elsewhere(
    preload, caplog
):
    """In the gunicorn master, whose SIGCHLD handler reaps every child, asyncio
    warns of every git op it finds reaped already."""
    reaped = "Unknown child process pid 4242, will report returncode 255"

    async def _sync(**kwargs):
        logging.getLogger("asyncio").warning(reaped)
        logging.getLogger("asyncio").warning("something else")

    with caplog.at_level(logging.WARNING, logger="asyncio"):
        preload(_sync)
        logging.getLogger("asyncio").warning(reaped)

    messages = [r.getMessage() for r in caplog.records if r.name == "asyncio"]
    assert messages == ["something else", reaped]


def test_the_preload_closes_a_clone_lock_left_open_before_the_workers_are_forked(
    git_origin, tmp_path, preload
):
    """A clone's lock fd still open in the gunicorn master would be held in
    every worker forked from it, for as long as each lives."""
    clone = GitPolicyFetcher.base_dir(tmp_path) / "0123abcd-0"
    _clone_at(clone, git_origin.url, git_origin.url)
    left = []

    async def _sync(**kwargs):
        left.append(git_cli.take_clone_lock(clone))

    records = []
    sink = opal_common_logger.logger.add(
        lambda m: records.append(m.record), level="ERROR"
    )
    try:
        preload(_sync)
    finally:
        opal_common_logger.logger.remove(sink)

    assert left[0] is not None
    assert git_cli._lock_fds == {}
    assert _lock_is_free(clone)
    assert any(str(clone_lock_path(clone)) in r["message"] for r in records)


@pytest.mark.parametrize("cli", [True, False], ids=["cli", "libgit2"])
def test_a_clone_the_sweep_cannot_read_neither_stops_the_preload_nor_the_sweep(
    cli, git_origin, tmp_path, monkeypatch, preload
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    clones = GitPolicyFetcher.base_dir(tmp_path)
    good = clones / "9999ffff-0"
    _clone_at(good, git_origin.url, git_origin.url)
    left = _plant_leftovers(good)
    bad = clones / "0000aaaa-0"  # swept first
    (bad / ".git").mkdir(parents=True)
    bad.chmod(0)
    synced = []

    async def _sync(**kwargs):
        synced.append(True)

    records = []
    sink = opal_common_logger.logger.add(
        lambda m: records.append(m.record), level="WARNING"
    )
    try:
        if os.access(bad, os.R_OK):
            pytest.skip("this user reads every directory (root)")
        preload(_sync)
    finally:
        bad.chmod(0o700)
        opal_common_logger.logger.remove(sink)

    assert synced == [True]
    assert [p for p in left if p.exists()] == []
    assert any(str(bad) in r["message"] for r in records)


def test_a_clones_directory_the_sweep_cannot_list_is_logged_and_left(tmp_path):
    clones = tmp_path / "git_sources"
    clones.mkdir()
    clones.chmod(0)
    records = []
    sink = opal_common_logger.logger.add(
        lambda m: records.append(m.record), level="WARNING"
    )
    try:
        if os.access(clones, os.R_OK):
            pytest.skip("this user reads every directory (root)")
        sweep_clone_leftovers(clones)
    finally:
        clones.chmod(0o700)
        opal_common_logger.logger.remove(sink)

    assert [r["message"] for r in records if str(clones) in r["message"]] == [
        f"Not sweeping {clones}: PermissionError(13, 'Permission denied')"
    ]


def test_a_sweep_that_fails_as_a_whole_does_not_stop_the_preload(
    tmp_path, monkeypatch, preload
):
    def _broken(base_dir):
        raise RuntimeError("the sweep broke")

    monkeypatch.setattr(task_module, "sweep_scope_clone_leftovers", _broken)
    synced = []

    async def _sync(**kwargs):
        synced.append(True)

    preload(_sync)

    assert synced == [True]


# --- sh, its watchdog and the kill grace -------------------------------------------


def _git_shim(tmp_path: Path, monkeypatch, body: str) -> None:
    """A ``git`` first on PATH that runs ``body`` (sh), never exec'ing, so its
    command line (with the clone's path in it) stays in the process table."""
    shims = tmp_path / "gitbin"
    shims.mkdir(exist_ok=True)
    (shims / "git").write_text(f"#!/bin/sh\n{body}\n")
    (shims / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")


@pytest.mark.parametrize("timeout", [60, 0], ids=["timeout", "no-timeout"])
@_LOOPS
def test_a_git_that_kills_its_own_sh_fails_at_once(
    loop, timeout, git_origin, tmp_path, monkeypatch, processes_with
):
    """Git kills the sh it runs under, and runs on.

    sh's watchdog outlives sh, and under uvloop every member of the
    group holds copies of sh's pipes: the op ends once sh is reaped (-1:
    no status came back), the watchdog taking git with it; not at its
    timeout, nor never without one.
    """
    pytest.importorskip(loop)
    marker = f"killsh-{uuid.uuid4().hex}"
    clone = tmp_path / marker
    _clone_at(clone, git_origin.url, git_origin.url)
    _git_shim(tmp_path, monkeypatch, "kill -9 $PPID\nwhile :; do sleep 1; done")

    async def main():
        start = time.monotonic()
        with pytest.raises(GitCliError) as info:
            await asyncio.wait_for(
                cli_fetch(
                    clone,
                    "origin",
                    _source(git_origin.url),
                    prune=False,
                    timeout=timeout,
                ),
                90,
            )
        return time.monotonic() - start, info.value.returncode

    elapsed, returncode = _run(loop, main)

    assert returncode == -1
    assert elapsed < 30  # not at the 60 s timeout
    _wait_until(lambda: processes_with(marker) == [])


@_LOOPS
def test_the_kill_grace_holds_for_a_git_that_ignores_sigterm(
    loop, git_origin, tmp_path, monkeypatch, processes_with
):
    """At the timeout the group gets SIGTERM.

    sh traps it and waits for git, and the watchdog ignores it, so git
    gets its whole grace before SIGKILL: sh's end does not cut it short.
    """
    pytest.importorskip(loop)
    timeout, grace = _SHIM_TIMEOUT, 2.0
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", grace)
    marker = f"grace-{uuid.uuid4().hex}"
    clone = tmp_path / marker
    _clone_at(clone, git_origin.url, git_origin.url)
    _git_shim(tmp_path, monkeypatch, "trap '' TERM\nwhile :; do sleep 1; done")

    async def main():
        start = time.monotonic()
        with pytest.raises(GitCliTimeoutError):
            await cli_fetch(
                clone, "origin", _source(git_origin.url), prune=False, timeout=timeout
            )
        return time.monotonic() - start

    elapsed = _run(loop, main)

    assert timeout + grace - 0.3 <= elapsed <= timeout + grace + 10
    _wait_until(lambda: processes_with(marker) == [])


_GRACE_WORKER = textwrap.dedent(
    """
    import asyncio, sys
    from pathlib import Path
    from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
    from opal_server.config import opal_server_config
    from opal_server.git_cli import cli_fetch

    opal_server_config.SCOPES_GIT_CLI_KILL_GRACE = 60.0
    source = GitPolicyScopeSource(
        source_type="git", url=sys.argv[3], branch="master",
        auth=NoAuthData(auth_type="none"),
    )
    main = cli_fetch(
        Path(sys.argv[2]), "origin", source, prune=False, timeout=float(sys.argv[4])
    )
    if sys.argv[1] == "uvloop":
        import uvloop
        loop = uvloop.new_event_loop()
    else:
        loop = asyncio.new_event_loop()
    loop.run_until_complete(main)
    """
)


@_LOOPS
def test_a_worker_killed_during_the_kill_grace_takes_git_with_it(
    loop, git_origin, tmp_path, monkeypatch, processes_with
):
    """The SIGTERM of a stop does not end the watchdog, so a worker SIGKILLed
    while git sits out its grace still leaves no member of the group behind.

    The stop is the op's timeout's, which starts once git's start is
    over: a cancel could come while asyncio still starts sh, whose stop
    is SIGKILL.
    """
    pytest.importorskip(loop)
    marker = f"midgrace-{uuid.uuid4().hex}"
    clone = tmp_path / marker
    _clone_at(clone, git_origin.url, git_origin.url)
    termed = tmp_path / "termed"
    _git_shim(
        tmp_path,
        monkeypatch,
        f"trap ': > \"{termed}\"' TERM\nwhile :; do sleep 1; done",
    )
    worker = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _GRACE_WORKER,
            loop,
            str(clone),
            git_origin.url,
            str(_SHIM_TIMEOUT),
        ],
        stderr=subprocess.PIPE,
    )
    try:
        _wait_until(termed.exists, timeout=_READY_SECONDS + _SHIM_TIMEOUT)
        assert processes_with(marker), "git did not sit out its grace"
        worker.kill()
        worker.wait()
        # Long before the 60 s grace could have ended.
        _wait_until(lambda: processes_with(marker) == [])
    finally:
        worker.kill()
        worker.communicate()


_REPACK_WORKER = textwrap.dedent(
    """
    import sys
    from opal_server import git_fetcher

    git_fetcher._repack_clone(sys.argv[1], 600)
    """
)


def test_a_worker_killed_mid_repack_takes_the_repack_with_it(
    git_origin, tmp_path, monkeypatch, processes_with
):
    """Git repack holds the clone's lock too: left to run, an orphaned repack
    would keep the clone from every sync for as long as it runs."""
    marker = f"repack-{uuid.uuid4().hex}"
    clone = tmp_path / "clones" / marker
    _clone_at(clone, git_origin.url, git_origin.url)
    _git_shim(tmp_path, monkeypatch, "while :; do sleep 1; done")
    worker = subprocess.Popen(
        [sys.executable, "-c", _REPACK_WORKER, str(clone)], stderr=subprocess.PIPE
    )
    try:
        _wait_until(
            lambda: any("repack" in a for _, _, a in processes_with(marker)),
            timeout=30,
        )
        worker.kill()
        worker.wait()
        start = time.monotonic()
        _wait_until(lambda: processes_with(marker) == [], timeout=5)
        ended_in = time.monotonic() - start
    finally:
        worker.kill()
        worker.communicate()

    assert ended_in <= 1.5
    # git's sleep, which holds the lock too and names no clone, dies with the
    # group a moment later.
    _wait_until(lambda: _lock_is_free(clone), timeout=5)


# --- the lock's own I/O, and the deletes of a clone -------------------------------


@pytest.mark.asyncio
async def test_a_cancel_while_the_clone_lock_is_taken_leaves_it_free_and_clear(
    git_origin, tmp_path, monkeypatch
):
    """The lock is taken, and the op recorded in it, on an executor thread; a
    caller cancelled meanwhile leaves no fd and no record behind, and the op is
    over (on_gone) only once that thread's work is."""
    real = git_cli._take_and_record
    events = []
    taking, release = threading.Event(), threading.Event()

    def _held(repo_path):
        taking.set()
        release.wait(_READY_SECONDS)
        try:
            return real(repo_path)
        finally:
            events.append("lock taken")

    monkeypatch.setattr(git_cli, "_take_and_record", _held)
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, git_origin.url)
    task = asyncio.ensure_future(
        cli_fetch(
            clone,
            "origin",
            _source(git_origin.url),
            prune=False,
            timeout=60,
            on_gone=events.append,
        )
    )
    loop = asyncio.get_running_loop()
    assert await loop.run_in_executor(None, taking.wait, _READY_SECONDS)

    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _until(lambda: len(events) == 2)

    assert events == ["lock taken", False]
    assert git_cli._lock_fds == {}
    assert _lock_is_free(clone)
    assert clone_lock_path(clone).read_bytes() == b""


def test_the_loop_ending_while_a_given_up_start_takes_the_lock_leaves_no_fd(
    git_origin, tmp_path, monkeypatch
):
    """A start given up on finishes its op under a lock of its own, polled for
    on an executor thread.

    The loop ending while that thread takes it leaves no fd open once
    the thread is done.
    """
    real = git_cli.take_clone_lock
    calls = []
    taking, release = threading.Event(), threading.Event()

    def _held_after_the_first(repo_path):
        calls.append(repo_path)
        if len(calls) > 1:  # not start's own, the finish's
            taking.set()
            release.wait(_READY_SECONDS)
        return real(repo_path)

    async def _refused(*args, **kwargs):
        raise OSError(24, "Too many open files")

    monkeypatch.setattr(git_cli, "take_clone_lock", _held_after_the_first)
    monkeypatch.setattr(git_cli.asyncio, "create_subprocess_exec", _refused)
    clone = tmp_path / "cli"
    _clone_at(clone, git_origin.url, git_origin.url)

    async def main():
        with pytest.raises(GitCliLocalError):
            await cli_fetch(
                clone, "origin", _source(git_origin.url), prune=False, timeout=60
            )
        loop = asyncio.get_running_loop()
        assert await loop.run_in_executor(None, taking.wait, _READY_SECONDS)
        # The finish's thread is taking the lock: it may go on once the loop's
        # end has cancelled the finish.
        (finish,) = [t for t in git_cli._background if t.get_loop() is loop]
        finish.add_done_callback(lambda _: release.set())

    _run("asyncio", main)

    assert len(calls) == 2
    assert git_cli._lock_fds == {}
    assert _lock_is_free(clone)


def _break_objects(clone: Path) -> None:
    for name in ("pack",):
        for path in (clone / ".git" / "objects" / name).iterdir():
            path.unlink()
    for path in (clone / ".git" / "objects").iterdir():
        if len(path.name) == 2:
            shutil.rmtree(path)


@pytest.mark.parametrize("what", ["invalid clone", "not a clone"])
@pytest.mark.asyncio
async def test_a_clone_another_process_s_git_holds_is_never_deleted(
    what, git_origin, tmp_path, orphan, monkeypatch
):
    """The deletes before a clone (an invalid clone's, or what is in the way of
    one) skip a clone whose lock a git op of another process holds, as the git
    command-line ops themselves do."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    emitted = []
    monkeypatch.setattr(
        metrics, "increment", lambda m, tags=None: emitted.append((m, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda m, v, tags=None: None)
    source = _source(git_origin.url)
    base = tmp_path / "base"
    fetcher = GitPolicyFetcher(base, "scope-1", source, callbacks=_Recorder())
    clone = GitPolicyFetcher.repo_clone_path(base, source)
    if what == "invalid clone":
        await fetcher.fetch_and_notify_on_changes()
        GitPolicyFetcher.reset_caches()
        _break_objects(clone)
    else:
        clone.mkdir(parents=True)
        (clone / "file").write_text("x")
    orphan(clone)

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert clone.exists()
    assert ("opal_server.scopes.git_op_skipped", {"reason": "clone_busy"}) in emitted


@pytest.mark.asyncio
async def test_a_deleted_scope_s_clone_another_process_s_git_holds_is_kept(
    git_origin, tmp_path, orphan
):
    clone = tmp_path / "clones" / "src"
    _clone_at(clone, git_origin.url, git_origin.url)
    orphan(clone)

    assert await git_fetcher_module.remove_clone_dir_exclusive(str(clone)) is False
    assert clone.exists()


def _lock_files_of_clones_that_are_gone(clones: Path, orphan) -> dict:
    """In ``clones``: a clone with its lock file, lock files whose clone never
    existed or was removed (one recording a dead op), one beside a directory a
    clone was being made in, one another process holds, and other dotted names;
    the paths by role."""
    live = clones / "live"
    url = str(clones.parent / "origin-not-used")
    clones.mkdir(parents=True, exist_ok=True)
    live.mkdir()
    pygit2.init_repository(str(live))
    pygit2.Repository(str(live)).remotes.create("origin", url)
    for name, record in (("live", ""), ("gone", ""), ("dead", "4194303\n")):
        clone_lock_path(clones / name).write_text(record)
    clone_lock_path(clones / "half").write_text("")
    half_made = clones / ".half.clone-0123456789abcdef"
    (half_made / ".git").mkdir(parents=True)
    orphan(clones / "held")
    others = [
        clones / ".gone.known_hosts.lock",
        clones / ".libgit2-home",
        clones / ".x.y.lock",
        clones / "gone.hung",
    ]
    for path in others:
        path.write_text("")
    return {
        "removed": [clone_lock_path(clones / n) for n in ("gone", "dead", "half")],
        "kept": [clone_lock_path(clones / n) for n in ("live", "held")] + others,
        "half made": half_made,
    }


@pytest.mark.fetch_backend("both")
def test_the_pre_fork_sweep_removes_the_lock_files_of_clones_that_are_gone(
    tmp_path, orphan
):
    """Every op on a clone, and every delete of one, takes its lock file, a
    delete of a scope that was never cloned included; nothing else removes a
    lock file whose clone is gone. With either fetch backend, the pre-fork
    sweep removes each one it can lock whose clone is not there and has no
    directory being made, once what a dead op left is gone, and logs how many;
    a lock another process holds, the lock of a clone and other dotted names
    stay.

    Mutation: dropping the check for the clone's directory removes the
    live clone's lock; skipping the lock-only names keeps every one.
    """
    base = tmp_path / "base"
    clones = GitPolicyFetcher.base_dir(base)
    paths = _lock_files_of_clones_that_are_gone(clones, orphan)

    with capture_records() as logs:
        git_fetcher_module.sweep_scope_clone_leftovers(base)

    assert [p for p in paths["removed"] if p.exists()] == []
    assert not paths["half made"].exists()
    assert [p for p in paths["kept"] if not p.exists()] == []
    assert [r["message"] for r in logs.emitted if "lock file" in r["message"]] == [
        f"Removed 3 lock files of clones no longer in {clones}"
    ]


def test_a_lock_file_that_cannot_be_removed_is_logged_and_the_sweep_goes_on(
    tmp_path, orphan, monkeypatch
):
    base = tmp_path / "base"
    clones = GitPolicyFetcher.base_dir(base)
    paths = _lock_files_of_clones_that_are_gone(clones, orphan)
    stuck = clone_lock_path(clones / "gone")
    unlink = os.unlink

    def _unlink(path, *args, **kwargs):
        if Path(path) == stuck:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(git_cli.os, "unlink", _unlink)

    with capture_records() as logs:
        git_fetcher_module.sweep_scope_clone_leftovers(base)

    assert stuck.exists()
    assert [p for p in paths["removed"] if p != stuck and p.exists()] == []
    assert [
        (r["level"].name, r["message"])
        for r in logs.emitted
        if "lock file" in r["message"]
    ] == [
        (
            "WARNING",
            f"Could not remove the lock file {stuck} of a clone that is gone: "
            "PermissionError(13, 'Permission denied')",
        ),
        ("INFO", f"Removed 2 lock files of clones no longer in {clones}"),
    ]


def test_the_lock_of_a_clone_whose_leftovers_stay_is_kept(
    tmp_path, orphan, monkeypatch
):
    """A directory a clone was being made in that cannot be removed keeps the
    dead op recorded in the lock file, for the next op to try again: the lock
    file stays with it.

    Mutation: removing the lock file whatever the leftovers' removal says.
    """
    base = tmp_path / "base"
    clones = GitPolicyFetcher.base_dir(base)
    paths = _lock_files_of_clones_that_are_gone(clones, orphan)
    remove_tree = git_cli.remove_tree

    def _remove_tree(path):
        if Path(path) == paths["half made"]:
            return False
        return remove_tree(path)

    monkeypatch.setattr(git_cli, "remove_tree", _remove_tree)

    git_fetcher_module.sweep_scope_clone_leftovers(base)

    assert paths["half made"].exists()
    assert clone_lock_path(clones / "half").exists()
    assert not clone_lock_path(clones / "gone").exists()


@pytest.mark.parametrize("code", [errno.ENOLCK, errno.EBADF], ids=["ENOLCK", "EBADF"])
def test_lock_files_stay_where_the_sweep_cannot_lock_them(
    tmp_path, orphan, monkeypatch, code
):
    """With flock failing (a clones directory on NFS without local_lock=flock),
    a lock file that cannot be locked is never removed, and the sweep does not
    raise."""
    base = tmp_path / "base"
    clones = GitPolicyFetcher.base_dir(base)
    paths = _lock_files_of_clones_that_are_gone(clones, orphan)
    _flock_fails_with(monkeypatch, code)

    git_fetcher_module.sweep_scope_clone_leftovers(base)

    assert [p for p in paths["removed"] + paths["kept"] if not p.exists()] == []


@pytest.mark.parametrize("stray", [".lock", "..clone-0123456789abcdef"])
def test_a_stray_name_with_no_source_id_is_not_swept_as_a_clone(tmp_path, stray):
    """A file named ``.lock``, or a directory named like a clone being made for
    an empty source id, names no clone: the sweep leaves it, and never takes
    the clones directory itself for one (no ``.git_sources.lock`` beside it).

    Mutation: accepting an empty source id sweeps git_sources as a clone.
    """
    base = tmp_path / "base"
    clones = GitPolicyFetcher.base_dir(base)
    clones.mkdir(parents=True)
    path = clones / stray
    if stray == ".lock":
        path.write_text("")
    else:
        path.mkdir()

    git_fetcher_module.sweep_scope_clone_leftovers(base)

    assert path.exists()
    assert sorted(p.name for p in clones.parent.iterdir()) == ["git_sources"]
