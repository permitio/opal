"""Starting a git command-line op's sh costs the event loop next to nothing.

The server's workers run uvloop, whose subprocess_exec forks the whole
worker and runs every at-fork hook of the process on the loop's thread
(an APM tracer's stop and restart of its threads, a metrics client's
flush): 20-50 ms per git op on a worker of 1-2 GiB, with the loop held,
and a sync pass starts one per clone. CPython's subprocess.Popen starts sh
with vfork and runs no at-fork hook (there is no preexec_fn). A hook that
sleeps when it runs stands in for the costly ones: a ticker on the loop
measures the stall while an op fetches.
"""

import asyncio
import errno
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional

import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.tests.log_capture import capture_records, starting_with
from opal_server import git_cli
from opal_server.config import opal_server_config
from opal_server.git_cli import GitCliError, GitCliLocalError, cli_fetch

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

# How long the at-fork hook sleeps when it runs, and the most the loop may lag
# while an op starts git: on the loop the lag is at least the hook's sleep.
HOOK_SECONDS = 0.3
MAX_LAG_SECONDS = 0.15
TICK_SECONDS = 0.01


class _AtForkHook:
    """One before-fork hook for the whole test session (os.register_at_fork
    cannot take one back): while armed, each call is counted and sleeps."""

    def __init__(self) -> None:
        self.armed = threading.Event()
        self.calls = 0
        os.register_at_fork(before=self._before)

    def _before(self) -> None:
        if self.armed.is_set():
            self.calls += 1
            threading.Event().wait(HOOK_SECONDS)


_hook = None


@pytest.fixture
def at_fork_hook():
    global _hook
    if _hook is None:
        _hook = _AtForkHook()
    _hook.calls = 0
    _hook.armed.set()
    try:
        yield _hook
    finally:
        _hook.armed.clear()


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)


def _run(loop: str, main):
    """Run ``main()`` on a new event loop of this kind, ending it as
    asyncio.run does."""
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


async def _max_loop_lag_during(coro) -> float:
    """How late, at most, a loop tick woke while ``coro`` ran."""
    loop = asyncio.get_running_loop()
    lags = []
    done = asyncio.Event()

    async def _tick():
        while not done.is_set():
            started = loop.time()
            await asyncio.sleep(TICK_SECONDS)
            lags.append(loop.time() - started - TICK_SECONDS)

    ticker = asyncio.create_task(_tick())
    await asyncio.sleep(TICK_SECONDS * 3)
    try:
        await coro
    finally:
        done.set()
        await ticker
    return max(lags)


@pytest.mark.parametrize("loop", ["asyncio", "uvloop"])
def test_starting_git_runs_no_at_fork_hook_and_never_stalls_the_loop(
    loop, git_origin, tmp_path, at_fork_hook
):
    """Mutation: starting sh with the event loop's subprocess_exec (as
    asyncio.create_subprocess_exec does) runs the hook on uvloop and fails
    here."""
    pytest.importorskip(loop)
    clone = tmp_path / "cli"
    pygit2.clone_repository(git_origin.url, str(clone)).free()
    source = GitPolicyScopeSource(
        source_type="git",
        url=git_origin.url,
        branch="master",
        auth=NoAuthData(auth_type="none"),
    )

    async def main():
        return await _max_loop_lag_during(
            cli_fetch(Path(clone), "origin", source, prune=False, timeout=60)
        )

    lag = _run(loop, main)

    assert at_fork_hook.calls == 0, "starting git ran the process's at-fork hooks"
    assert lag < MAX_LAG_SECONDS, f"the event loop stalled {lag:.2f}s starting git"


# --- how sh is reaped ---------------------------------------------------------

needs_pidfd = pytest.mark.skipif(
    not hasattr(os, "pidfd_open"), reason="pidfd_open is Linux's"
)


# subprocess.Popen itself: the sh_starts fixture puts a function in its place.
_POPEN = subprocess.Popen


class _Interrupted(BaseException):
    """A BaseException that is no OSError, raised once sh runs."""


def _source(url: str) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git", url=url, branch="master", auth=NoAuthData(auth_type="none")
    )


def _clone(git_origin, tmp_path: Path, url: Optional[str] = None) -> Path:
    clone = tmp_path / "cli"
    pygit2.clone_repository(git_origin.url, str(clone)).free()
    if url is not None:
        repo = pygit2.Repository(str(clone))
        try:
            repo.remotes.set_url("origin", url)
        finally:
            repo.free()
    return clone


@pytest.fixture
def sh_starts(monkeypatch):
    """Every sh git_cli starts (subprocess.Popen objects), and the names of the
    threads started meanwhile."""
    made: List[subprocess.Popen] = []
    threads: List[str] = []
    popen = subprocess.Popen
    start = threading.Thread.start

    def _popen(args, *rest, **kwargs):
        proc = popen(args, *rest, **kwargs)
        if list(args[:3]) == [git_cli._SH, "-c", git_cli._STATUS_SCRIPT]:
            made.append(proc)
        return proc

    def _start(self):
        threads.append(self.name)
        return start(self)

    monkeypatch.setattr(git_cli.subprocess, "Popen", _popen)
    monkeypatch.setattr(threading.Thread, "start", _start)
    return made, threads


@pytest.fixture
def thread_errors(monkeypatch):
    """What any thread raised and did not catch."""
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args))
    return errors


async def _until(predicate, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, "the condition never held"
        await asyncio.sleep(0.02)


def _reaped(proc: subprocess.Popen, seconds: float = 10.0) -> bool:
    """Whether ``proc`` is reaped within ``seconds``, by whatever reaps it (a
    poll here would reap it itself: only its returncode is read)."""
    deadline = time.monotonic() + seconds
    while proc.returncode is None:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)
    return True


@needs_pidfd
@pytest.mark.parametrize("loop", ["asyncio", "uvloop"])
def test_on_linux_the_loop_watches_sh_through_a_pidfd_and_starts_no_thread(
    loop, git_origin, tmp_path, sh_starts
):
    """Mutation: reaping sh on a thread of its own (no pidfd) fails here."""
    pytest.importorskip(loop)
    made, threads = sh_starts
    clone = _clone(git_origin, tmp_path)

    _run(
        loop,
        lambda: cli_fetch(
            clone, "origin", _source(git_origin.url), prune=False, timeout=60
        ),
    )

    assert len(made) == 1 and made[0].returncode is not None
    assert [name for name in threads if name.startswith("git-sh-")] == []


@pytest.mark.parametrize(
    "no_pidfd", ["missing", "ENOSYS", "EPERM"], ids=["missing", "ENOSYS", "EPERM"]
)
@pytest.mark.parametrize("loop", ["asyncio", "uvloop"])
def test_without_a_pidfd_a_thread_reaps_sh(
    loop, no_pidfd, git_origin, tmp_path, monkeypatch, sh_starts
):
    """Where pidfd_open is missing (macOS) or the kernel refuses it."""
    pytest.importorskip(loop)
    if no_pidfd == "missing":
        monkeypatch.delattr(os, "pidfd_open", raising=False)
    else:
        code = getattr(errno, no_pidfd)

        def _refused(pid, flags=0):
            raise OSError(code, os.strerror(code))

        monkeypatch.setattr(os, "pidfd_open", _refused, raising=False)
    made, threads = sh_starts
    clone = _clone(git_origin, tmp_path)

    _run(
        loop,
        lambda: cli_fetch(
            clone, "origin", _source(git_origin.url), prune=False, timeout=60
        ),
    )

    assert len(made) == 1 and _reaped(made[0])
    assert [name for name in threads if name.startswith("git-sh-")] == [
        f"git-sh-{made[0].pid}"
    ]


@pytest.mark.parametrize("reaping", ["pidfd", "thread"])
@pytest.mark.parametrize("loop", ["asyncio", "uvloop"])
def test_sh_is_reaped_after_the_loop_has_ended_and_no_thread_raises(
    loop,
    reaping,
    git_origin,
    tmp_path,
    blackhole,
    monkeypatch,
    sh_starts,
    thread_errors,
):
    """The loop ends while git still runs (its op is cancelled, and the stop
    after it by the loop's end): sh is reaped once it is gone, by a thread,
    whose hand-off of the status to the closed loop raises nothing.

    Mutation: the reaper thread not catching the closed loop's RuntimeError
    reports a thread exception here (thread); the loop's end not handing sh
    to a thread leaves it unreaped (pidfd).
    """
    pytest.importorskip(loop)
    if reaping == "pidfd" and not hasattr(os, "pidfd_open"):
        pytest.skip("pidfd_open is Linux's")
    if reaping == "thread":
        monkeypatch.delattr(os, "pidfd_open", raising=False)
    made, _ = sh_starts
    wait = _POPEN.wait

    def _late(self, timeout=None):
        # Hands sh's status over well after the loop has closed.
        returncode = wait(self, timeout)
        if self in made:
            time.sleep(0.5)
        return returncode

    monkeypatch.setattr(_POPEN, "wait", _late)
    clone = _clone(git_origin, tmp_path, f"http://127.0.0.1:{blackhole}/hung.git")

    async def main():
        op = asyncio.ensure_future(
            cli_fetch(clone, "origin", _source(git_origin.url), prune=False, timeout=60)
        )
        await _until(lambda: made)
        op.cancel()
        await asyncio.sleep(0)

    _run(loop, main)

    assert len(made) == 1 and _reaped(made[0])
    time.sleep(1.0)  # the hand-off comes 0.5 s after the reap
    assert thread_errors == []


@pytest.mark.parametrize("loop", ["asyncio", "uvloop"])
def test_a_reaper_thread_that_cannot_start_is_a_local_failure_and_sh_is_reaped(
    loop, git_origin, tmp_path, monkeypatch, sh_starts
):
    """No pidfd, and no thread to wait for sh: the op fails as a local failure,
    ends, and sh is still reaped once its watchdog has ended it.

    Mutation: Thread.start's RuntimeError not turned into an OSError fails
    the op with a RuntimeError; sh not reaped after it leaves a zombie.
    """
    pytest.importorskip(loop)
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    made, _ = sh_starts
    start = threading.Thread.start

    def _start(self):
        if self.name.startswith("git-sh-"):
            raise RuntimeError("can't start new thread")
        return start(self)

    monkeypatch.setattr(threading.Thread, "start", _start)
    clone = _clone(git_origin, tmp_path)
    gone = []

    async def main():
        with pytest.raises(GitCliLocalError, match="cannot start a thread to reap sh"):
            await cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=gone.append,
            )
        await _until(lambda: gone and made[0].returncode is not None)

    _run(loop, main)

    assert gone == [False]
    assert made[0].returncode is not None


@pytest.mark.parametrize("loop", ["asyncio", "uvloop"])
def test_a_start_that_raises_no_oserror_once_sh_runs_raises_it_and_ends(
    loop, git_origin, tmp_path, monkeypatch, sh_starts
):
    """Anything else raised once sh runs goes to the caller as it is; the op
    still ends, and sh is reaped."""
    pytest.importorskip(loop)
    made, _ = sh_starts

    def _interrupted(proc):
        raise _Interrupted()

    monkeypatch.setattr(git_cli, "_Reaper", _interrupted)
    clone = _clone(git_origin, tmp_path)
    gone = []

    async def main():
        with pytest.raises(_Interrupted):
            await cli_fetch(
                clone,
                "origin",
                _source(git_origin.url),
                prune=False,
                timeout=60,
                on_gone=gone.append,
            )
        await _until(lambda: gone and made[0].returncode is not None)

    _run(loop, main)

    assert gone == [False]
    assert made[0].returncode is not None


def test_a_reaper_thread_whose_wait_fails_logs_it_and_ends_the_op(
    git_origin, tmp_path, monkeypatch, sh_starts
):
    """A wait for sh that raises on its thread is logged at ERROR and taken for
    sh's end: the op stops git and fails, rather than wait for good with its
    clone locked.

    Mutation: the thread not catching the wait's error leaves the op
    waiting for good (the test times out).
    """
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    made, _ = sh_starts
    wait = _POPEN.wait

    def _fails(self, timeout=None):
        if self in made:
            raise MemoryError("no memory to wait")
        return wait(self, timeout)

    monkeypatch.setattr(_POPEN, "wait", _fails)
    clone = _clone(git_origin, tmp_path)

    async def main():
        with pytest.raises(GitCliError, match="killed before it reported"):
            await asyncio.wait_for(
                cli_fetch(
                    clone, "origin", _source(git_origin.url), prune=False, timeout=60
                ),
                30,
            )

    with capture_records() as logs:
        _run("asyncio", main)

    [error] = starting_with(logs.emitted, "Could not wait for the sh of git")
    assert error["level"].name == "ERROR"
    assert git_cli.clone_lock_path(clone).read_bytes() == b""
    monkeypatch.setattr(_POPEN, "wait", wait)
    assert made[0].wait(10) is not None
