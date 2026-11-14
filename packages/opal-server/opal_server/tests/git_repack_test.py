"""The scope-clone repack: the primitive (``_count_pack_files``,
``_repack_clone``), the ref steps it starts with (pack-refs, reflogs off and
removed), the repack lock it runs under, its wiring into the scope
sync (a fetch marks the clone due, ``GitPolicyFetcher.run_due_repacks`` ends
the sync pass by repacking it), and the GitPython handles on scope
clones that must be closed for a repack's deleted packs to free their disk.

The repository tests use real git: a bare remote and a libgit2 clone of it,
the way the scopes fetcher builds its clones. A libgit2 clone of a local path
starts with loose objects, and every fetch after it writes exactly one new pack
that nothing ever merges; that growth is what the repack exists to undo.

The process-control tests put a ``git`` shim on PATH instead, because a real
repack cannot be made to hang on cue.
"""

import asyncio
import datetime
import errno
import fcntl
import math
import os
import select
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import weakref
from pathlib import Path

import git
import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_common.async_utils import run_sync
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.log_capture import capture_records
from opal_server import git_cli, git_fetcher
from opal_server.config import OpalServerConfig, opal_server_config
from opal_server.git_fetcher import (
    GitConcurrencyLimitExceeded,
    GitNotFoundError,
    GitPolicyFetcher,
    GitRepackError,
    GitRepackIncompleteError,
    PolicyFetcherCallbacks,
    _count_pack_files,
    _repack_clone,
    _repack_timeout_seconds,
    git_op_in_flight,
)
from opal_server.scopes.purge import purge_local_memory
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import NewCommitsCallbacks, ScopesService

# What these tests stub or measure is libgit2's fetch and clone.
pytestmark = pytest.mark.fetch_backend("libgit2")

_SIG = pygit2.Signature("opal-test", "opal-test@example.com")


def _init_remote(path: Path) -> pygit2.Repository:
    """A bare remote whose HEAD is refs/heads/master, the branch _commit
    writes, whatever init.defaultBranch the user's git config sets."""
    return pygit2.init_repository(str(path), bare=True, initial_head="master")


def _commit(repo: pygit2.Repository, content: str, parent=None) -> pygit2.Oid:
    blob = repo.create_blob(content.encode())
    builder = repo.TreeBuilder()
    builder.insert("policy.rego", blob, pygit2.enums.FileMode.BLOB)
    parents = [parent] if parent is not None else []
    return repo.create_commit(
        "refs/heads/master", _SIG, _SIG, content, builder.write(), parents
    )


def _clone_with_fetch_packs(tmp_path: Path, fetches: int):
    """A libgit2 clone holding one pack per fetch, plus every commit id."""
    remote = _init_remote(tmp_path / "remote.git")
    tip = _commit(remote, "package policy\n")
    commits = [tip]
    clone_path = tmp_path / "clone"
    clone = pygit2.clone_repository(str(tmp_path / "remote.git"), str(clone_path))
    for i in range(fetches):
        tip = _commit(remote, f"package policy\n# rev {i}\n", tip)
        commits.append(tip)
        clone.remotes["origin"].fetch()
    clone.free()
    remote.free()
    return clone_path, commits


def _pack_dir(repo_path: Path) -> Path:
    return repo_path / ".git" / "objects" / "pack"


def _git_temp_names(repo_path: Path) -> list:
    return sorted(
        n for n in os.listdir(_pack_dir(repo_path)) if n.startswith(("tmp_", ".tmp-"))
    )


def test_count_pack_files_missing_dir_is_zero(tmp_path):
    assert _count_pack_files(tmp_path / "never-cloned") == 0


def test_count_pack_files_counts_only_packs_with_their_index(tmp_path):
    """The one definition of a pack, for the trigger, the logged count and
    the success check alike: a ``pack-*.pack`` with its ``.idx``."""
    pack = _pack_dir(tmp_path / "clone")
    pack.mkdir(parents=True)
    for name in (
        "pack-aaaa.pack",
        "pack-aaaa.idx",
        "pack-bbbb.pack",  # a repack died between its two renames
        "pack-cccc.idx",  # libgit2 commits the .idx first
        ".tmp-7-pack-dddd.pack",
        "tmp_pack_Ab12Cd",
        "pack_git2_0cfe7f06b9343d09",
    ):
        (pack / name).write_bytes(b"x")
    assert _count_pack_files(tmp_path / "clone") == 1


def test_repack_merges_fetch_packs_into_one_and_keeps_every_commit(tmp_path):
    clone_path, commits = _clone_with_fetch_packs(tmp_path, fetches=5)
    assert _count_pack_files(clone_path) == 5  # the premise: one pack per fetch

    _repack_clone(clone_path, timeout=60)

    assert _count_pack_files(clone_path) == 1
    assert _git_temp_names(clone_path) == []
    fresh = pygit2.Repository(str(clone_path))
    try:
        # Including the clone-time commit, which was a loose object until
        # the repack packed it (and -d's prune-packed deleted the loose copy).
        for oid in commits:
            assert fresh.get(oid) is not None, oid
        assert fresh.revparse_single("refs/remotes/origin/master").id == commits[-1]
    finally:
        fresh.free()
    subprocess.run(
        ["git", "-C", str(clone_path), "fsck", "--no-progress"],
        check=True,
        capture_output=True,
    )


def _git(
    repo_path: Path, *args: str, check: bool = True, stdin: str | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=check,
        capture_output=True,
        text=True,
        input=stdin,
    )


def test_repack_keeps_a_packed_object_no_ref_names_yet(tmp_path):
    """A fetch in another process installs its pack first and moves its ref
    afterwards, so a repack can list that pack while nothing names its objects
    yet. They must survive: the fetch then points the ref at them.

    The other fetch is a pack-objects writing straight into the clone's
    pack dir, holding a commit (and its tree and blob) no ref reaches.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    remote = pygit2.Repository(str(tmp_path / "remote.git"))
    try:
        blob = remote.create_blob(b"package policy\n# landing\n")
        builder = remote.TreeBuilder()
        builder.insert("policy.rego", blob, pygit2.enums.FileMode.BLOB)
        landing = str(
            remote.create_commit(
                None,
                _SIG,
                _SIG,
                "landing",
                builder.write(),
                [remote.head.target],
            )
        )
    finally:
        remote.free()
    _git(
        tmp_path / "remote.git",
        "pack-objects",
        "--revs",
        "-q",
        str(_pack_dir(clone_path) / "pack"),
        stdin=f"{landing}\n",
    )
    assert _count_pack_files(clone_path) == 3
    assert _git(clone_path, "cat-file", "-t", landing).stdout.strip() == "commit"

    _repack_clone(clone_path, timeout=60)

    assert _count_pack_files(clone_path) == 1
    assert _git(clone_path, "cat-file", "-t", landing, check=False).returncode == 0, (
        "the repack deleted an object a landing fetch is about to point a ref at"
    )
    _git(clone_path, "update-ref", "refs/heads/landed", landing)
    _git(clone_path, "fsck", "--no-progress")


def test_repack_writes_no_dumb_http_catalog(tmp_path):
    """No update-server-info: nothing serves a scope clone over dumb HTTP.

    By default ``git repack`` also runs ``git update-server-info``, which
    writes ``.git/info/refs`` with one line per ref: 7 MB on each clone of a
    61k-branch repository, rewritten on every repack while the clone's lock
    is held.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=3)

    _repack_clone(clone_path, timeout=60)

    assert _count_pack_files(clone_path) == 1
    assert not (clone_path / ".git" / "info" / "refs").exists()
    assert not (clone_path / ".git" / "objects" / "info" / "packs").exists()


def test_handle_opened_before_repack_reads_every_commit_after(tmp_path):
    """The cached pygit2 handle survives the packs it knows being deleted.

    libgit2 treats an object missing from the packs it has loaded as a
    miss, re-scans the pack directory and retries, so a handle opened
    (and used) before the repack still finds every object in the new
    pack afterwards.
    """
    clone_path, commits = _clone_with_fetch_packs(tmp_path, fetches=5)
    held = pygit2.Repository(str(clone_path))
    try:
        assert held.get(commits[1]) is not None  # loads one of the fetch packs
        _repack_clone(clone_path, timeout=60)
        assert _count_pack_files(clone_path) == 1
        for oid in commits:
            assert held.get(oid) is not None, oid
        assert held.revparse_single("refs/remotes/origin/master").id == commits[-1]
    finally:
        held.free()


# --- process control, with a `git` shim on PATH --------------------------------


def _install_git_shim(
    tmp_path: Path, monkeypatch, body: str, *, refs_steps: bool = False
) -> Path:
    """Put a ``git`` running ``body`` first on PATH.

    The repack's ref steps (``git -C <clone> config`` and ``git -C <clone>
    pack-refs``) succeed without running it, unless ``refs_steps`` hands
    them to ``body`` too.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    skip = "" if refs_steps else 'case "$3" in config|pack-refs) exit 0;; esac\n'
    shim.write_text("#!/bin/sh\n" + skip + body)
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def _fake_clone(tmp_path: Path) -> Path:
    """A clone dir with a real-looking pack, the temp file of a repack that
    died, and one named like libgit2's indexer temp."""
    clone_path = tmp_path / "clone"
    pack = _pack_dir(clone_path)
    pack.mkdir(parents=True)
    for name in ("pack-aaaa.pack", "pack-aaaa.idx", "tmp_pack_stale", "pack_git2_old"):
        (pack / name).write_bytes(b"x")
    return clone_path


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A killed orphan is a zombie until init reaps it: dead, just not gone.
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return True  # no /proc (macOS): launchd reaps orphans promptly
    return state != "Z"


def _wait_gone(pid: int, deadline_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + deadline_seconds
    while _pid_alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def _wait_for(condition, deadline_seconds: float = 30.0) -> bool:
    deadline = time.monotonic() + deadline_seconds
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def _hold_lock(path: Path) -> int:
    """Take the repack lock on the directory ``path`` the way another
    process would: through an open file of its own. Returns its fd."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def _reap(pid: int, deadline_seconds: float = 5.0) -> None:
    """Reap a forked child, SIGKILLing it first if it is still alive at the
    deadline: a test waits for its child, never hangs on it."""
    deadline = time.monotonic() + deadline_seconds
    while os.waitpid(pid, os.WNOHANG) == (0, 0):
        if time.monotonic() > deadline:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            return
        time.sleep(0.01)


def _lock_is_free(path: Path) -> bool:
    """Whether the repack lock on the directory ``path`` can be taken,
    probing it the way another process would: through an open file of its
    own."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(fd)  # releases the probe's own lock, if it took one
    return True


def _clone_lock_is_free(clone_path: Path) -> bool:
    fd = git_cli.take_clone_lock(clone_path)
    if fd is None:
        return False
    git_cli.drop_clone_lock(fd)
    return True


def _free_once_a_stop_returns(probe) -> bool:
    """``probe()`` (a lock is free) as a stop returns.

    On macOS within a few
    seconds: its kill() answers for a member still exiting, its fds open, as
    for a zombie, so a stop can return a moment before the last of them has
    closed its copy of the lock. Linux reads /proc, where a member is a
    zombie only once its files are closed.
    """
    if git_cli.EPERM_MEANS_NO_LIVE_MEMBER:
        return _wait_for(probe, deadline_seconds=5.0)
    return probe()


@pytest.mark.parametrize("ignores_term", [False, True], ids=["term", "kill"])
def test_timeout_stops_git_and_removes_its_temp_packs(
    tmp_path, monkeypatch, records, ignores_term
):
    """A repack past its timeout is stopped with its whole process group, and
    what it left in the pack dir is removed; nothing else is.

    The shim leaves what a killed repack leaves (pack-objects' ``tmp_pack_*``,
    repack's ``.tmp-<pid>-pack-*``, and a ``.pack`` installed without its
    ``.idx``: git renames the ``.pack`` first and the ``.idx`` last), plus a
    file named like libgit2's indexer temp, and runs a background child
    standing in for pack-objects. In the "kill" case the shim ignores SIGTERM
    from its first line, and so does its child, so only the SIGKILL fallback
    after the grace period ends them.
    """
    clone_path = _fake_clone(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    if ignores_term:
        # Ignored, not trapped: a trap has to be scheduled within the grace
        # to say it ran, which a starved runner does not always do. A child
        # inherits the ignored signal.
        head = "trap '' TERM\n"
        child = "/bin/sleep 30 &"
        tail = f': > "{state}/ready"\nwhile :; do /bin/sleep 1; done\n'
    else:
        head = ""
        child = "/bin/sleep 30 &"
        tail = f': > "{state}/ready"\nwait\n'
    _install_git_shim(
        tmp_path,
        monkeypatch,
        head + f'pack="$2/.git/objects/pack"\n'
        f': > "$pack/tmp_pack_Ab12Cd"\n'
        f': > "$pack/.tmp-$$-pack-0123abcd.pack"\n'
        f': > "$pack/.tmp-$$-pack-0123abcd.idx"\n'
        f': > "$pack/pack-0123abcd.pack"\n'
        f': > "$pack/pack-0123abcd.rev"\n'
        f': > "$pack/pack_git2_Zz9Yy8"\n'
        f'echo $$ > "{state}/leader.pid"\n'
        f"{child}\n"
        f'echo $! > "{state}/child.pid"\n' + tail,
    )
    # The timeout is also the shim's window to get to "ready" (and, in the
    # "kill" case, to install its TERM trap first): generous for a slow runner.
    # The "kill" grace also has to cover a starved runner scheduling the trap.
    timeout, grace = 3.0, (1.0 if ignores_term else 5.0)

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        _repack_clone(clone_path, timeout=timeout, term_grace=grace)
    elapsed = time.monotonic() - started

    assert (state / "ready").exists(), "shim never got going; test proves nothing"
    leader = int((state / "leader.pid").read_text())
    child_pid = int((state / "child.pid").read_text())
    assert _wait_gone(leader), "git itself still running"
    assert _wait_gone(child_pid), "git's child (pack-objects) still running"
    if ignores_term:
        # SIGTERM went to the group first, and the group outlived its grace.
        assert [
            r
            for r in records
            if r["level"].name == "WARNING" and "sending SIGKILL" in r["message"]
        ]
        assert elapsed >= timeout + grace  # waited out the grace, then killed
    else:
        assert elapsed < timeout + grace  # SIGTERM alone ended it
    assert sorted(os.listdir(_pack_dir(clone_path))) == [
        "pack-aaaa.idx",
        "pack-aaaa.pack",
        "pack_git2_Zz9Yy8",  # libgit2's name: never ours to delete
        "pack_git2_old",
    ]  # tmp_pack_stale went before git started: see the next test
    assert git_fetcher._repack_lock_fds == set()
    assert _lock_is_free(git_fetcher._repack_lock_dir(clone_path))


def test_a_sigkill_stop_returns_once_nothing_of_the_group_holds_its_lock(tmp_path):
    """The SIGKILL of a stop ends sh before sh can reap its watchdog, which
    holds sh's copy of the lock git inherits and no stderr: the stop returns
    only once it is gone too, and the lock is free then, 20 times in a row.

    Mutation: returning once stderr is closed leaves the watchdog holding the
    lock for a moment after the stop, which under CPU load fails this.
    """
    lock_dir = tmp_path / "clones"
    lock_dir.mkdir()
    for i in range(20):
        ready = tmp_path / f"ready{i}"
        fd = _hold_lock(lock_dir)
        watched, watching = os.pipe()
        try:
            proc = subprocess.Popen(
                git_fetcher._watched_argv(
                    ["/bin/sh", "-c", ': > "$1"; exec /bin/sleep 30', "sh", str(ready)]
                ),
                stdin=watched,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
                pass_fds=(fd,),
            )
        finally:
            os.close(watched)
        try:
            # The watchdog is forked before the command runs.
            assert _wait_for(ready.exists), "the command never ran"
        finally:
            os.close(fd)  # the group's copies are the lock's only holders now
            stopped = git_fetcher._stop_repack(proc, 0.0)
            os.close(watching)
        assert stopped is True
        assert _free_once_a_stop_returns(lambda: _lock_is_free(lock_dir)), (
            f"stop {i}: the lock is still held"
        )


def test_leftovers_of_a_dead_repack_are_removed_before_git_runs(tmp_path, monkeypatch):
    """Under the repack lock no other repack is alive, so every git temp file
    in the pack dir, and every pack without its index, was left by one that
    died, say one orphaned by a killed leader and later killed itself, and
    nothing else ever removes it.

    libgit2's files stay: its in-flight names, and a fetched pack's ``.idx``
    committed before its ``.pack`` (measured on libgit2 1.9.7).
    """
    clone_path = _fake_clone(tmp_path)
    pack = _pack_dir(clone_path)
    for name in (
        ".tmp-999-pack-dead.pack",
        ".tmp-999-pack-dead.idx",
        "pack-aaaa.rev",  # an indexed pack's: stays with it
        "pack-cccc.pack",  # killed between git's renames of .pack and .idx,
        "pack-cccc.rev",  # which come in this order (git 2.41+ writes .rev)
        "pack-cccc.mtimes",
        "pack-cccc.bitmap",
        "pack-cccc.promisor",
        "pack-dddd.idx",  # libgit2 about to link in pack-dddd.pack
        "pack_git2_0cfe7f06b9343d09",
        "pack_git2_0cfe7f06b934idx.lock",
    ):
        (pack / name).write_bytes(b"x")
    seen = tmp_path / "seen"
    _install_git_shim(
        tmp_path, monkeypatch, f'ls -1A "$2/.git/objects/pack" > "{seen}"\n'
    )

    assert _repack_clone(clone_path, timeout=60) is True

    assert sorted(seen.read_text().split()) == [
        "pack-aaaa.idx",
        "pack-aaaa.pack",
        "pack-aaaa.rev",
        "pack-dddd.idx",
        "pack_git2_0cfe7f06b9343d09",
        "pack_git2_0cfe7f06b934idx.lock",
        "pack_git2_old",
    ]


def test_pack_whose_index_the_listing_missed_stays(tmp_path, monkeypatch):
    """A listing is no snapshot: one taken while libgit2 installs a pack can
    hold its ``.pack`` and miss the ``.idx`` renamed in just before it. Such a
    pack is checked on disk and kept; a pack truly without its index goes."""
    pack = _pack_dir(tmp_path / "clone")
    pack.mkdir(parents=True)
    for name in (
        "pack-eeee.pack",
        "pack-eeee.idx",
        "pack-eeee.rev",
        "pack-ffff.pack",
        "pack-ffff.rev",
    ):
        (pack / name).write_bytes(b"x")
    real_names = git_fetcher._pack_dir_names

    def _names_but_the_index(path):
        names = real_names(path)
        assert names is not None  # the dir is there
        return names - {"pack-eeee.idx"}

    monkeypatch.setattr(git_fetcher, "_pack_dir_names", _names_but_the_index)

    git_fetcher._remove_repack_leftovers(pack, "in this test")

    assert sorted(os.listdir(pack)) == [
        "pack-eeee.idx",
        "pack-eeee.pack",
        "pack-eeee.rev",
    ]


@pytest.mark.parametrize(
    "exists, stderr_says",
    [(True, "not a git repository"), (False, "cannot change to")],
    ids=["plain-dir", "missing-dir"],
)
def test_nonzero_exit_raises_git_repack_error_with_stderr_tail(
    tmp_path, exists, stderr_says
):
    """Real git failing is GitRepackError, never FileNotFoundError: even a
    clone dir that vanished must not read as "git is not installed"."""
    target = tmp_path / "not-a-clone"
    if exists:
        target.mkdir()
    with pytest.raises(GitRepackError) as info:
        _repack_clone(target, timeout=60)
    assert info.value.returncode != 0
    assert stderr_says in info.value.stderr_tail


def test_failed_repack_removes_its_temp_packs_and_keeps_only_the_tail(
    tmp_path, monkeypatch
):
    """Git does not clean up after a pack-objects that dies (ENOSPC, OOM):

    its tmp_pack_* stays behind, on the very disk the repack exists to
    free.
    """
    clone_path = _fake_clone(tmp_path)
    _install_git_shim(
        tmp_path,
        monkeypatch,
        ': > "$2/.git/objects/pack/tmp_pack_Qw3Er4"\n'
        "i=0; while [ $i -lt 400 ]; do echo 'warning: noise noise noise' >&2;"
        " i=$((i+1)); done\n"
        "echo 'fatal: the final words' >&2\n"
        "exit 3\n",
    )
    with pytest.raises(GitRepackError) as info:
        _repack_clone(clone_path, timeout=60)
    assert info.value.returncode == 3
    assert info.value.stderr_tail.endswith("fatal: the final words")
    assert len(info.value.stderr_tail) <= git_fetcher._REPACK_STDERR_TAIL_CHARS
    assert "fatal: the final words" in str(info.value)
    assert _git_temp_names(clone_path) == []
    assert "pack_git2_old" in os.listdir(_pack_dir(clone_path))


def test_exit_zero_that_leaves_packs_behind_is_a_failure(tmp_path, monkeypatch):
    """Exit 0 with more than one pack left is a failed repack.

    ``-a -d`` leaves exactly one pack, so the status lied. That is what a
    SIGCHLD reaper elsewhere in the process does; here SIGCHLD is ignored,
    the kernel reaps the failed git before subprocess can, and subprocess
    then reports exit 0.
    """
    clone_path = _fake_clone(tmp_path)
    # A real repack starts at the pack limit, so a git that failed leaves
    # several of the packs it started with: two here.
    pack = _pack_dir(clone_path)
    for name in ("pack-cccc.pack", "pack-cccc.idx"):
        (pack / name).write_bytes(b"x")
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'pack="$2/.git/objects/pack"\n'
        ': > "$pack/pack-bbbb.pack"\n: > "$pack/pack-bbbb.idx"\n'
        ': > "$pack/tmp_pack_Zx9Cv8"\n'
        "exit 1\n",
    )
    previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    try:
        with pytest.raises(GitRepackIncompleteError) as info:
            _repack_clone(clone_path, timeout=60)
    finally:
        signal.signal(signal.SIGCHLD, previous)
    assert info.value.packs == 2
    assert _git_temp_names(clone_path) == []  # cleaned up like any failure


def test_cleanup_that_cannot_list_the_pack_dir_never_hides_the_failure(
    tmp_path, monkeypatch, records
):
    """The sweep after a failure is best-effort: an EIO listing the pack dir
    is logged, and the caller still sees git's own error."""
    clone_path = _fake_clone(tmp_path)
    _install_git_shim(tmp_path, monkeypatch, "echo 'fatal: disk on fire' >&2\nexit 5\n")
    pack = _pack_dir(clone_path)
    real_scandir = os.scandir

    def _scandir(path="."):
        if Path(path) == pack:
            raise OSError(errno.EIO, "Input/output error", str(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", _scandir)
    with pytest.raises(GitRepackError) as info:
        _repack_clone(clone_path, timeout=60)
    assert info.value.returncode == 5
    assert "disk on fire" in info.value.stderr_tail
    assert [
        r
        for r in records
        if r["level"].name == "WARNING" and r["message"].startswith("Could not list")
    ], "the failed listing was not logged"


def test_sweeping_the_clones_dir_mid_repack_lets_no_second_repack_run(
    tmp_path, monkeypatch
):
    """The lock is the clones' directory itself, so deleting everything in it
    but the clones (an orphan sweep, say) while a repack runs leaves nothing
    that would let a second one start beside it and sweep the first one's
    files."""
    clones_dir = tmp_path / "git_sources"
    clone_path = clones_dir / "clone"
    _pack_dir(clone_path).mkdir(parents=True)
    (clones_dir / "stray").write_bytes(b"x")  # something for the sweep to take
    assert git_fetcher._repack_lock_dir(clone_path) == clones_dir
    state = tmp_path / "state"
    state.mkdir()
    _install_git_shim(
        tmp_path,
        monkeypatch,
        f'if [ -e "{state}/first" ]; then echo run >> "{state}/second"; exit 0; fi\n'
        f': > "{state}/first"\n'
        f'find "{clones_dir}" -mindepth 1 -maxdepth 1 ! -name clone -exec rm -rf {{}} +\n'
        f': > "{state}/swept"\n'
        f'while [ ! -e "{state}/release" ]; do /bin/sleep 0.05; done\n',
    )
    first: dict = {}

    def _first_repack():
        try:
            first["result"] = _repack_clone(clone_path, timeout=60)
        except BaseException as e:  # reported below, not lost in the thread
            first["result"] = e

    thread = threading.Thread(target=_first_repack)
    thread.start()
    try:
        assert _wait_for(lambda: (state / "swept").exists()), "first repack never ran"
        assert _repack_clone(clone_path, timeout=60) is False
        assert not (state / "second").exists()
    finally:
        (state / "release").touch()
        thread.join(30)
    assert first == {"result": True}
    assert sorted(os.listdir(clones_dir)) == ["clone"]


# --- the repack lock -------------------------------------------------------------


def _flock_fails_with(monkeypatch, code: int) -> None:
    """Make every flock raise ``code``: what a clones directory on an NFS mount
    without local_lock=flock answers (ENOLCK), or a read-only fd asked for an
    exclusive lock there (EBADF)."""

    def _flock(fd, operation):
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(git_fetcher.fcntl, "flock", _flock)


@pytest.mark.parametrize("code", [errno.ENOLCK, errno.EBADF], ids=["ENOLCK", "EBADF"])
def test_lock_that_cannot_be_taken_raises_and_keeps_no_fd(tmp_path, monkeypatch, code):
    """Not "another repack holds it" (that is a skip): the repack fails, and
    the fd opened for the lock is closed, not left in the set the fork handler
    closes in every child."""
    clone_path = _fake_clone(tmp_path)
    runs = tmp_path / "runs"
    _install_git_shim(tmp_path, monkeypatch, f'echo run >> "{runs}"\n')
    _flock_fails_with(monkeypatch, code)

    with pytest.raises(OSError) as info:
        _repack_clone(clone_path, timeout=60)

    assert info.value.errno == code
    assert git_fetcher._repack_lock_fds == set()
    assert not runs.exists()


def test_one_lock_for_every_clone_in_the_directory(tmp_path):
    """One lock per pod holds only while every scope clone sits directly in
    the one clones directory: checked through the fetcher's own layout."""
    clones = [
        GitPolicyFetcher.repo_clone_path(
            tmp_path,
            GitPolicyScopeSource(
                source_type="git", url=url, branch="master", auth=NoAuthData()
            ),
        )
        for url in ("https://example.com/a.git", "https://example.com/b.git")
    ]
    assert clones[0] != clones[1]
    assert {git_fetcher._repack_lock_dir(c) for c in clones} == {
        GitPolicyFetcher.base_dir(tmp_path)
    }


def test_repack_leaves_nothing_but_the_clones_in_their_directory(tmp_path, monkeypatch):
    """No repack lock file: nothing an orphan sweep of the clones directory
    could delete, and so let a second repack in. Only the clone's own lock
    file (git_cli.clone_lock_path), which the repack shares with the clone's
    git command-line ops."""
    clones_dir = tmp_path / "git_sources"
    _pack_dir(clones_dir / "clone").mkdir(parents=True)
    _install_git_shim(tmp_path, monkeypatch, "exit 0\n")
    assert _repack_clone(clones_dir / "clone", timeout=60) is True
    assert sorted(os.listdir(clones_dir)) == [".clone.lock", "clone"]


def test_repack_leaves_no_descriptor_open(tmp_path, monkeypatch):
    """Not the locks', and not the watchdog pipe's: an open write end of that
    pipe would keep a later orphaned repack's watchdog from ever firing."""
    clone_path = _fake_clone(tmp_path)
    _install_git_shim(tmp_path, monkeypatch, "exit 0\n")
    assert _repack_clone(clone_path, timeout=60) is True  # what is set up for good
    fds = sorted(os.listdir("/dev/fd"))

    assert _repack_clone(clone_path, timeout=60) is True

    assert sorted(os.listdir("/dev/fd")) == fds


def test_repack_is_skipped_while_another_repack_holds_the_lock(tmp_path, monkeypatch):
    """Another process's repack, of any clone next to this one, means this
    one does not run at all: skipped, not waited for, and not swept."""
    clone_path = _fake_clone(tmp_path)
    runs = tmp_path / "runs"
    _install_git_shim(tmp_path, monkeypatch, f'echo run >> "{runs}"\n')
    lock = git_fetcher._repack_lock_dir(clone_path)
    held = _hold_lock(lock)
    try:
        assert _repack_clone(clone_path, timeout=60) is False
        assert not runs.exists()
        # Not this repack's to remove while another may be writing it.
        assert "tmp_pack_stale" in os.listdir(_pack_dir(clone_path))
        assert git_fetcher._repack_lock_fds == set()
    finally:
        os.close(held)
    assert _repack_clone(clone_path, timeout=60) is True
    assert runs.read_text().split() == ["run"]
    assert _lock_is_free(lock)


def _group_left(pgid: int) -> bool:
    """Whether any process, a zombie included, is left in the group
    ``pgid``."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # macOS: members that have exited, not yet reaped
    return True


def test_back_to_back_repacks_each_run_and_leave_both_locks_free(tmp_path, monkeypatch):
    """A repack returns only once nothing of its git is left, so nothing holds
    the repack's or the clone's lock: sh reaps the watchdog it SIGKILLs before
    it exits (the watchdog, a fork of sh, holds sh's copies of both). A repack
    right after another runs, and a probe finds both locks free.

    Mutation: sh exiting right after SIGKILLing its watchdog leaves the
    watchdog in its group, holding both locks, until something else reaps it:
    under CPU load (12 busy processes on 8 CPUs) long enough to fail this,
    and to skip most repacks that follow at once; on an idle machine the
    watchdog is mostly gone in time.
    """
    groups: list = []
    real_popen = subprocess.Popen

    class _RecordingPopen(real_popen):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            groups.append(self.pid)  # each step's group: sh is its leader

    monkeypatch.setattr(git_fetcher.subprocess, "Popen", _RecordingPopen)
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=1)
    for _ in range(20):
        assert _repack_clone(clone_path, timeout=60) is True
        assert len(groups) == 3  # config, pack-refs, repack
        assert [g for g in groups if _group_left(g)] == []
        groups.clear()
        assert _lock_is_free(git_fetcher._repack_lock_dir(clone_path))
        assert _clone_lock_is_free(clone_path)


def test_a_leader_killed_mid_repack_takes_its_git_with_it(tmp_path, monkeypatch):
    """A leader SIGKILLed mid-repack (gunicorn's WORKER TIMEOUT, an OOM kill)
    leaves no git behind holding the locks.

    git runs in a session of its own, which no signal to the leader
    reaches, but under the watchdog of the git command-line fetch (see
    _repack_argv), which kills git's whole group, every child that holds
    the locks included (a stand-in for pack-objects here), once the
    leader's end of its pipe is gone. The next leader's repack then
    runs.
    """
    clone_path = _fake_clone(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    real_path = os.environ["PATH"]
    shim_dir = _install_git_shim(
        tmp_path,
        monkeypatch,
        f'echo $$ >> "{state}/runs"\n'
        f'( while [ ! -e "{state}/release" ]; do /bin/sleep 0.05; done ) &\n'
        f'echo $! > "{state}/child.pid"\n'
        f': > "{state}/ready"\n'
        "wait\n",
    )
    # The shim goes on the leader's PATH only after its imports: importing
    # GitPython runs `git version`.
    leader = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os\n"
            "from opal_server.git_fetcher import _repack_clone\n"
            f"os.environ['PATH'] = {str(shim_dir)!r} + os.pathsep + os.environ['PATH']\n"
            f"_repack_clone({str(clone_path)!r}, timeout=60)\n",
        ],
        env={**os.environ, "PATH": real_path, "PYTHONPATH": os.pathsep.join(sys.path)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        started = _wait_for(lambda: (state / "ready").exists())
    finally:
        leader.kill()
        _, leader_stderr = leader.communicate()
    assert started, f"git never started: {leader_stderr.decode()[-2000:]}"
    lock = git_fetcher._repack_lock_dir(clone_path)
    [git_pid] = [int(p) for p in (state / "runs").read_text().split()]
    child_pid = int((state / "child.pid").read_text())
    try:
        assert _wait_gone(child_pid) and _wait_gone(git_pid)
        # The rest of the group (sh, the watchdog, the child's sleep) holds
        # the lock too, and dies with it a moment later.
        assert _wait_for(lambda: _lock_is_free(lock))
    finally:
        (state / "release").touch()
    assert _repack_clone(clone_path, timeout=60) is True
    assert len((state / "runs").read_text().split()) == 2


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")
# Python warns on fork() with threads alive, as it would in the gunicorn
# master this stands in for; the child below makes nothing but raw syscalls.
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded:DeprecationWarning"
)
def test_forked_child_closes_its_copy_of_the_lock_without_unlocking_it(tmp_path):
    """The gunicorn master forks workers while a preload repack of its may
    still run.

    A worker's inherited copy of the lock fd would hold the lock for the
    worker's whole life; the fork handler closes it, and must not unlock
    it, which would release the parent's (and its git's) lock too.
    """
    lock = tmp_path  # the clones' directory
    fd = git_fetcher._take_repack_lock(lock)
    assert fd is not None
    locked = os.stat(lock)
    to_child_r, to_child_w = os.pipe()
    to_parent_r, to_parent_w = os.pipe()
    pid = os.fork()
    if pid == 0:  # the forked child: report, then live on until its pipe closes
        try:
            os.close(to_parent_r)
            os.close(to_child_w)
            try:
                held = os.fstat(fd)
                # Compared, not only fstat'd: the fd number reused for some
                # other file must not read as "kept".
                closed = int(
                    (held.st_dev, held.st_ino) != (locked.st_dev, locked.st_ino)
                )
            except OSError:
                closed = 1
            still_locked = 0 if _lock_is_free(lock) else 1
            os.write(to_parent_w, b"%d%d" % (closed, still_locked))
            select.select([to_child_r], [], [], 10)  # EOF ends the wait
        finally:
            os._exit(0)
    # With the parent's own copies closed, a child that dies before it
    # reports reads as EOF below, and one that hangs as a timeout: a
    # failure either way, never a hung test.
    os.close(to_parent_w)
    os.close(to_child_r)
    try:
        ready, _, _ = select.select([to_parent_r], [], [], 10)
        assert ready, "the forked child never reported"
        report = os.read(to_parent_r, 2)
        assert report == b"11", "child kept its copy (1st) or unlocked it (2nd)"
        git_fetcher._drop_repack_lock(fd)
        # The child is still alive, and holds nothing.
        assert _lock_is_free(lock), "the forked child still holds the lock"
    finally:
        if fd in git_fetcher._repack_lock_fds:
            git_fetcher._drop_repack_lock(fd)
        os.close(to_child_w)  # the child's cue to exit
        os.close(to_parent_r)
        _reap(pid)


def test_repack_runs_git_with_expected_args_and_minimal_env(tmp_path, monkeypatch):
    """Only PATH/HOME-style variables reach git.

    An inherited GIT_DIR (or
    GIT_OBJECT_DIRECTORY, GIT_INDEX_FILE, ...) would override ``-C`` and repack
    a different repository; OPAL's own secrets have no business in git's env.
    """
    clone_path = _fake_clone(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    _install_git_shim(
        tmp_path,
        monkeypatch,
        f'printf \'%s\\n\' "$@" > "{out}/args"\n/usr/bin/env > "{out}/env"\n',
    )
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "some-other-repo.git"))
    monkeypatch.setenv("OPAL_AUTH_MASTER_TOKEN", "do-not-leak")

    _repack_clone(clone_path, timeout=60)

    assert (out / "args").read_text().splitlines() == [
        "-C",
        str(clone_path),
        "-c",
        "pack.threads=1",
        "-c",
        "pack.packSizeLimit=0",
        "repack",
        "-a",
        "-d",
        "-k",
        "-n",
        "-q",
    ]
    env = dict(
        line.split("=", 1)
        for line in (out / "env").read_text().splitlines()
        if "=" in line
    )
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["PATH"] == os.environ["PATH"]
    assert "GIT_DIR" not in env
    assert "OPAL_AUTH_MASTER_TOKEN" not in env


@pytest.mark.parametrize("kind", ["empty-string", "empty-dir", "unsearchable-dir"])
def test_missing_git_raises_git_not_found(tmp_path, monkeypatch, kind):
    """No git on PATH is GitNotFoundError, whatever else PATH holds.

    "unsearchable-dir" is a PATH entry the server's user cannot search
    (another user's home, say): a bare exec lookup then reports the
    EACCES from that entry (PermissionError) instead of "not found".
    """
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    locked = tmp_path / "locked-bin"
    locked.mkdir()
    path = {
        "empty-string": "",
        "empty-dir": str(empty),
        "unsearchable-dir": f"{locked}{os.pathsep}{empty}",
    }[kind]
    monkeypatch.setenv("PATH", path)
    monkeypatch.chdir(tmp_path)  # an empty PATH entry means the cwd
    locked.chmod(0)
    try:
        with pytest.raises(GitNotFoundError):
            _repack_clone(_fake_clone(tmp_path), timeout=60)
    finally:
        locked.chmod(stat.S_IRWXU)


@pytest.mark.parametrize(
    "configured, expected",
    [
        (12.5, 12.5),
        (0, 120.0),
        (-1.0, 120.0),
        (math.nan, 120.0),
        (math.inf, 120.0),
        (-math.inf, 120.0),
        (86400.0, 86400.0),
        (86401.0, 86400.0),
        (3_000_000, 86400.0),
    ],
)
def test_repack_timeout_seconds_never_means_no_limit(monkeypatch, configured, expected):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_TIMEOUT", configured)
    assert _repack_timeout_seconds() == expected


def test_timeout_over_a_day_is_capped_with_one_warning(monkeypatch, records):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_TIMEOUT", 3_000_000)

    assert _repack_timeout_seconds() == 86400.0
    assert _repack_timeout_seconds() == 86400.0

    [warning] = [r for r in records if r["level"].name == "WARNING"]
    assert "3000000" in warning["message"]
    assert "86400" in warning["message"]


def test_repack_given_a_huge_timeout_still_runs(tmp_path):
    """subprocess waits in a C int of milliseconds: past about 24.8 days
    communicate() raises OverflowError, and every repack would fail."""
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)

    assert _repack_clone(clone_path, timeout=3_000_000) is True

    assert _count_pack_files(clone_path) == 1


def test_repack_default_timeout_matches_the_config_default(monkeypatch):
    monkeypatch.delenv("OPAL_SCOPES_GIT_REPACK_TIMEOUT", raising=False)
    clean = OpalServerConfig(prefix="OPAL_")
    assert (
        git_fetcher._REPACK_DEFAULT_TIMEOUT_SECONDS == clean.SCOPES_GIT_REPACK_TIMEOUT
    )


def test_timeout_description_states_the_real_bounds():
    """The operator-facing bound, timeout plus 30 seconds, is these
    constants: change one and the description must change with it."""
    described = " ".join(
        opal_server_config.entries["SCOPES_GIT_REPACK_TIMEOUT"].description.split()
    )
    grace = git_fetcher._REPACK_TERM_GRACE_SECONDS
    stopping = grace + git_fetcher._REPACK_KILL_WAIT_SECONDS
    slack = git_fetcher._REPACK_EXECUTOR_SLACK_SECONDS
    default = git_fetcher._REPACK_DEFAULT_TIMEOUT_SECONDS
    assert f"then SIGKILL {grace:.0f} seconds later" in described
    assert f"Stopping git can take up to {stopping:.0f} seconds" in described
    assert f"up to {slack:.0f} seconds past the timeout" in described
    assert f"the timeout plus {slack:.0f} seconds" in described
    assert f"({default + slack:.0f} seconds with the default)" in described


@pytest.mark.parametrize("bad", [0.0, -5.0, math.nan, math.inf])
def test_repack_clone_refuses_to_run_unbounded(tmp_path, monkeypatch, bad):
    """Handed an unvalidated timeout, the primitive still applies the default
    (shrunk here so the test is quick) instead of waiting forever."""
    clone_path = _fake_clone(tmp_path)
    _install_git_shim(tmp_path, monkeypatch, "exec /bin/sleep 30\n")
    monkeypatch.setattr(git_fetcher, "_REPACK_DEFAULT_TIMEOUT_SECONDS", 0.3)
    with pytest.raises(TimeoutError):
        _repack_clone(clone_path, timeout=bad, term_grace=2.0)


# --- wired into the sync: GitPolicyFetcher.fetch_and_notify_on_changes ---------
#
# A real GitPolicyFetcher syncing a local bare remote. Its first sync clones
# (loose objects, no pack); every forced sync after a push fetches and adds one
# pack, so with the limit at 3 the third fetch is the one that marks the clone
# due, and the pass it is part of (``_ScopeRepo.sync_pass``) repacks it.

_LIMIT = 3


@pytest.fixture(autouse=True)
def _clean_fetcher_state(monkeypatch):
    """Limit 3, and a clean slate of the per-process state the sync keeps: the
    fetcher's class-level caches (as invalid_repo_recovery_test does) and the
    repack's due marks, failure cooldowns, git-missing latch and timeout-cap
    latch."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", _LIMIT)
    monkeypatch.setattr(git_fetcher, "_repack_git_missing", False)
    monkeypatch.setattr(git_fetcher, "_repack_failed_at", {})
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    monkeypatch.setattr(git_fetcher, "_repack_timeout_cap_logged", False)
    monkeypatch.setattr(git_fetcher, "_repack_limit_clamp_logged", False)
    monkeypatch.setattr(git_fetcher, "_sync_passes_in_flight", 0)
    monkeypatch.setattr(git_fetcher, "_orphan_index_first_seen", {})
    monkeypatch.setattr(git_fetcher, "_repack_cooldown_logged_at", {})
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    assert not git_fetcher._repack_lock.locked(), "a test leaked a running repack"
    assert git_fetcher._repack_lock_fds == set(), "a test leaked a repack lock fd"
    assert git_fetcher._sync_passes_in_flight == 0, "a test leaked a pass in flight"


@pytest.fixture
def emitted(monkeypatch):
    """Capture calls through the metrics facade (metrics_emission_test's
    pattern: every emitting module shares the one ``metrics`` module)."""
    calls = {"gauge": [], "increment": [], "distribution": []}
    monkeypatch.setattr(
        metrics,
        "gauge",
        lambda metric, value, tags=None: calls["gauge"].append((metric, value, tags)),
    )
    monkeypatch.setattr(
        metrics,
        "increment",
        lambda metric, tags=None: calls["increment"].append((metric, tags)),
    )
    monkeypatch.setattr(
        metrics,
        "distribution",
        lambda metric, value, tags=None: calls["distribution"].append(
            (metric, value, tags)
        ),
    )
    return calls


def _repack_outcomes(calls) -> list:
    return [
        tags["outcome"]
        for metric, tags in calls["increment"]
        if metric == "opal_server.scopes.git_repack"
    ]


def _pack_refs_outcomes(calls) -> list:
    return [
        tags["outcome"]
        for metric, tags in calls["increment"]
        if metric == "opal_server.scopes.git_pack_refs"
    ]


def _repack_seconds(calls) -> list:
    return [
        (value, tags)
        for metric, value, tags in calls["distribution"]
        if metric == "opal_server.scopes.git_repack_seconds"
    ]


def _skips(calls) -> list:
    return [
        tags
        for metric, tags in calls["increment"]
        if metric == "opal_server.scopes.git_op_skipped"
    ]


class _RecordingTracer:
    """The real ddtrace tracer, keeping every span it starts."""

    def __init__(self, real):
        self._real = real
        self.spans: list = []

    def trace(self, name, *args, **kwargs):
        span = self._real.trace(name, *args, **kwargs)
        self.spans.append(span)
        return span

    def repack_spans(self) -> list:
        return [s for s in self.spans if s.name == "git_policy_fetcher.repack"]

    def pack_refs_spans(self) -> list:
        return [s for s in self.spans if s.name == "git_policy_fetcher.pack_refs"]


@pytest.fixture
def spans(monkeypatch):
    recorder = _RecordingTracer(git_fetcher.tracer)
    monkeypatch.setattr(git_fetcher, "tracer", recorder)
    return recorder


@pytest.fixture
def records():
    captured = []
    sink = logger.add(lambda m: captured.append(m.record), level="DEBUG")
    yield captured
    logger.remove(sink)


class _RepackSpy:
    """Stands in for ``_repack_clone`` (or ``real``, ``_pack_clone_refs`` say):

    records each call, runs ``on_start``, then optionally blocks until ``gate``
    opens, then raises ``raises`` or runs the real one.
    """

    def __init__(
        self,
        raises: BaseException | None = None,
        gate=None,
        on_start=None,
        real=_repack_clone,
    ):
        self.raises = raises
        self.gate = gate
        self.on_start = on_start
        self.real = real
        self.calls: list = []
        self.started = threading.Event()

    def __call__(self, repo_path, timeout, **kwargs):
        self.calls.append(os.fspath(repo_path))
        if self.on_start is not None:
            self.on_start()
        self.started.set()
        if self.gate is not None:
            self.gate.wait(10)
        if self.raises is not None:
            raise self.raises
        return self.real(repo_path, timeout, **kwargs)


class _ScopeRepo:
    """A bare remote the test pushes to, and a scope fetcher syncing it.

    ``notified`` records every ``on_update`` as (old head, new head, pack
    count of the clone at that moment).
    """

    def __init__(self, tmp_path: Path, name: str):
        remote_path = tmp_path / f"{name}.git"
        self.remote = _init_remote(remote_path)
        self._revision = 0
        self.tip: pygit2.Oid | None = None
        self.push()
        self.notified: list = []
        outer = self

        class _Recorder(PolicyFetcherCallbacks):
            async def on_update(self, old_head, head):
                outer.notified.append(
                    (old_head, head, _count_pack_files(outer.clone_path))
                )

        self.fetcher = GitPolicyFetcher(
            base_dir=tmp_path / "base",
            scope_id=name,
            source=GitPolicyScopeSource(
                source_type="git",
                url=str(remote_path),
                branch="master",
                auth=NoAuthData(),
            ),
            callbacks=_Recorder(),
        )

    @property
    def clone_path(self) -> Path:
        return self.fetcher._repo_path

    @property
    def source_id(self) -> str:
        return self.fetcher._source_id

    def _next_content(self) -> str:
        self._revision += 1
        return f"package policy\n# rev {self._revision}\n"

    def push(self) -> pygit2.Oid:
        self.tip = _commit(self.remote, self._next_content(), self.tip)
        return self.tip

    def force_push(self, onto: pygit2.Oid) -> pygit2.Oid:
        """Rewrite the branch to a new commit on ``onto``, dropping the tip."""
        blob = self.remote.create_blob(self._next_content().encode())
        builder = self.remote.TreeBuilder()
        builder.insert("policy.rego", blob, pygit2.enums.FileMode.BLOB)
        rewritten = self.remote.create_commit(
            None, _SIG, _SIG, "rewrite", builder.write(), [onto]
        )
        self.remote.references["refs/heads/master"].set_target(rewritten)
        self.tip = rewritten
        return rewritten

    async def sync(self, **kwargs) -> None:
        """This scope's sync on its own, as a refresh runs it: it can mark the
        clone's repack due, never run it."""
        kwargs.setdefault("force_fetch", True)
        await self.fetcher.fetch_and_notify_on_changes(**kwargs)

    async def sync_pass(self, **kwargs) -> None:
        """A sync pass of this scope: its sync, then the due repacks the pass
        ends with. Every source marked due counts as live here; dropping the
        mark of a dead one has tests of its own."""
        await self.sync(**kwargs)
        await GitPolicyFetcher.run_due_repacks(set(git_fetcher._repacks_due))

    async def push_and_sync(self) -> str:
        tip = self.push()
        await self.sync_pass()
        return str(tip)

    async def fetched(self, times: int) -> None:
        """Clone, then fetch ``times`` pushes: ``times`` packs."""
        await self.sync()
        for _ in range(times):
            await self.push_and_sync()
        assert _count_pack_files(self.clone_path) == times


def _watch_free(handle: pygit2.Repository, path: str) -> list:
    """Record ``path`` in the returned list whenever ``handle.free()`` runs."""
    freed: list = []
    real_free = handle.free
    handle.free = lambda: (freed.append(path), real_free())
    return freed


@pytest.mark.asyncio
async def test_sync_repacks_the_clone_once_its_packs_reach_the_limit(
    tmp_path, emitted, records, spans
):
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    assert _repack_outcomes(emitted) == []  # below the limit: left alone
    path = str(scope.clone_path)
    freed = _watch_free(GitPolicyFetcher.repos[path], path)

    tip = await scope.push_and_sync()  # the fetch that reaches the limit

    assert _count_pack_files(scope.clone_path) == 1
    # PDPs heard about the new commit before the repack started.
    assert scope.notified[-1][1:] == (tip, _LIMIT)
    assert path not in GitPolicyFetcher.repos, (
        "the cached handle was kept, holding the deleted packs open"
    )
    assert freed == [path], "the cached handle was dropped but not free()'d"
    assert _repack_outcomes(emitted) == ["ok"]
    [(seconds, tags)] = _repack_seconds(emitted)
    assert seconds >= 0
    assert tags == {"outcome": "ok"}
    [done] = [r for r in records if r["message"].startswith("Repacked scope clone")]
    assert done["level"].name == "INFO"
    assert done["extra"]["packs_before"] == _LIMIT
    assert done["extra"]["packs_after"] == 1
    assert done["extra"]["bytes_before"] > 0
    assert done["extra"]["bytes_after"] > 0
    [span] = spans.repack_spans()
    assert span.resource == "s1"
    assert span.get_tag("skipped") is None

    # The next sync reopens the clone and both it and a bundle serve the
    # newest commit, full and as a diff against the pre-repack tip.
    newest = await scope.push_and_sync()
    assert scope.notified[-1][:2] == (tip, newest)
    assert path in GitPolicyFetcher.repos
    assert scope.fetcher.make_bundle().hash == newest
    diff = await run_sync(scope.fetcher.make_bundle, tip)
    assert (diff.old_hash, diff.hash) == (tip, newest)
    assert _repack_outcomes(emitted) == ["ok"]  # 2 packs now: nothing to do
    assert _skips(emitted) == []  # below the limit is not a skip worth a count


@pytest.mark.asyncio
async def test_repack_duration_is_no_longer_than_the_repack_call_took(
    tmp_path, emitted, records
):
    """The git_repack_seconds value, and the seconds in the "Repacked" line,
    lie between 0 and the wall time measured around the call that runs the
    repack.

    Mutation: adding or multiplying the clock readings instead of subtracting
    them gives a value of the order of the clock itself, far above the wall
    time; dividing them gives about 1, above it on a repack quicker than 1 s.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()  # the fetch that reaches the limit marks the clone due
    assert _repack_outcomes(emitted) == []

    before = time.monotonic()
    await GitPolicyFetcher.run_due_repacks(set(git_fetcher._repacks_due))
    wall = time.monotonic() - before

    assert _repack_outcomes(emitted) == ["ok"]
    [(seconds, _)] = _repack_seconds(emitted)
    assert 0 <= seconds <= wall
    [done] = [r for r in records if r["message"].startswith("Repacked scope clone")]
    assert done["extra"]["seconds"] == seconds


@pytest.mark.asyncio
async def test_repack_holds_lock_source_so_a_second_sync_of_the_clone_waits(
    tmp_path, monkeypatch
):
    """The due repack runs under the clone's lock_source.

    So nothing else in the process touches the clone until it is done: a
    second sync of the same source queues behind it (it neither runs nor
    skips on the busy marker), then completes.
    """
    gate = threading.Event()
    spy = _RepackSpy(gate=gate)
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)

    first = asyncio.ensure_future(scope.push_and_sync())
    second = None
    try:
        assert await run_sync(spy.started.wait, 5), "repack never started"
        assert GitPolicyFetcher.repo_locks[scope.source_id].locked()
        notified = len(scope.notified)
        second = asyncio.ensure_future(scope.push_and_sync())
        done, _ = await asyncio.wait({second}, timeout=0.5)
        assert not done, "a second sync of the clone ran while it was repacked"
        assert len(scope.notified) == notified
    finally:
        gate.set()
    await asyncio.wait_for(first, timeout=10)
    assert second is not None
    newest = await asyncio.wait_for(second, timeout=10)
    assert scope.notified[-1][1] == newest
    assert spy.calls == [str(scope.clone_path)]


@pytest.mark.asyncio
async def test_repack_running_in_another_process_is_a_skip(
    tmp_path, emitted, records, spans
):
    """A previous leader's orphaned git (any repack another process runs next
    to this clone) holds the repack lock: the sync skips, reports nothing as
    done and keeps its handle, and a later fetch repacks once it is gone.

    The skip is counted, and its span says it was one: a lock that is
    never released must not read as a string of millisecond repacks.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    path = str(scope.clone_path)
    held = _hold_lock(git_fetcher._repack_lock_dir(scope.clone_path))
    try:
        tip = await scope.push_and_sync()
        assert scope.notified[-1][1] == tip
        assert _count_pack_files(scope.clone_path) == _LIMIT
        assert _repack_outcomes(emitted) == []
        assert _skips(emitted) == [{"reason": "repack_running"}]
        [span] = spans.repack_spans()
        assert span.get_tag("skipped") == "repack_running"
        assert not [r for r in records if r["message"].startswith("Repacked")]
        assert path in GitPolicyFetcher.repos, "nothing was repacked: keep it"
        assert git_fetcher._repack_failed_at == {}  # a skip is not a failure
    finally:
        os.close(held)

    await scope.push_and_sync()
    assert _count_pack_files(scope.clone_path) == 1
    assert _repack_outcomes(emitted) == ["ok"]
    assert _skips(emitted) == [{"reason": "repack_running"}]
    assert spans.repack_spans()[-1].get_tag("skipped") is None


@pytest.mark.parametrize("limit", [0, -1])
@pytest.mark.asyncio
async def test_limit_of_zero_or_less_never_repacks(
    tmp_path, monkeypatch, emitted, limit
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", limit)
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")

    await scope.fetched(_LIMIT + 1)

    assert spy.calls == []
    assert _repack_outcomes(emitted) == []


@pytest.mark.asyncio
async def test_only_a_fetch_made_by_this_sync_marks_a_repack_due(tmp_path, monkeypatch):
    """A sync that fetched nothing added no pack (phase 2 of a pass), and a
    fetch that failed raised before the housekeeping; neither marks the clone
    due, even with the clone already at the limit."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", _LIMIT - 1)

    await scope.sync_pass(force_fetch=False)  # the branch is there: no fetch
    assert git_fetcher._repacks_due == {}
    assert spy.calls == []

    scope.remote.free()
    os.rename(tmp_path / "s1.git", tmp_path / "gone.git")
    with pytest.raises(pygit2.GitError):
        await scope.sync()
    assert git_fetcher._repacks_due == {}
    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    assert spy.calls == []
    assert _count_pack_files(scope.clone_path) == _LIMIT - 1


class _FailingCallbacks(PolicyFetcherCallbacks):
    """The notification of a scope that fails, for that scope alone (a publish
    that fails, say)."""

    async def on_update(self, old_head, head):
        raise RuntimeError("publish failed")


@pytest.mark.parametrize("op", ["clone", "fetch"])
@pytest.mark.asyncio
async def test_a_notification_that_fails_still_marks_the_clone_its_sync_wrote(
    tmp_path, op
):
    """The pack a fetch wrote, and the refs a libgit2 clone left each in a file
    of its own, are the clone's, whichever scope's sync wrote them: the sync
    that fails after its fetch or clone, in its change check or its
    notification, still marks the clone due, and fails all the same.

    Mutation: marking only after a notification that went out leaves the
    clone unmarked, and in a pass whose first scope on the clone fails
    this way, unmarked pass after pass.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    if op == "fetch":
        await scope.fetched(_LIMIT - 1)
        assert git_fetcher._repacks_due == {}
        scope.push()
    scope.fetcher.callbacks = _FailingCallbacks()

    with pytest.raises(RuntimeError, match="publish failed"):
        await scope.sync()

    assert set(git_fetcher._repacks_due) == {scope.source_id}


@pytest.mark.asyncio
async def test_only_packs_with_their_index_count_toward_the_limit(
    tmp_path, monkeypatch, records
):
    """What a dead repack left in the pack dir (a pack without its index, a
    staged temp pack) is no pack: it neither brings the repack forward nor
    shows in the logged counts, and the next repack removes it."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 2)
    pack = _pack_dir(scope.clone_path)
    leftovers = {"pack-0badc0de.pack", ".tmp-99-pack-0badc0de.pack"}
    for name in leftovers:
        (pack / name).write_bytes(b"x")

    await scope.push_and_sync()  # one pack short of the limit, leftovers aside
    assert spy.calls == []

    await scope.push_and_sync()  # the fetch that reaches the limit
    assert spy.calls == [str(scope.clone_path)]
    [done] = [r for r in records if r["message"].startswith("Repacked scope clone")]
    assert (done["extra"]["packs_before"], done["extra"]["packs_after"]) == (_LIMIT, 1)
    assert not leftovers & set(os.listdir(pack))


@pytest.mark.parametrize(
    "exc, outcome",
    [
        (GitRepackError(128, "fatal: no space left on device"), "error"),
        (TimeoutError("git repack exceeded 120.0s"), "timeout"),
        # Not "git is missing": the clones' dir, the lock, vanished.
        (FileNotFoundError(errno.ENOENT, "No such file", "git_sources"), "error"),
    ],
    ids=["error", "timeout", "vanished-dir"],
)
@pytest.mark.asyncio
async def test_failed_repack_still_completes_the_sync_and_waits_out_an_hour(
    tmp_path, monkeypatch, emitted, records, exc, outcome
):
    spy = _RepackSpy(raises=exc)
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    path = str(scope.clone_path)
    freed = _watch_free(GitPolicyFetcher.repos[path], path)

    tip = await scope.push_and_sync()  # must not raise

    assert spy.calls == [path]
    assert scope.notified[-1][1] == tip, "the sync did not complete"
    assert _count_pack_files(scope.clone_path) == _LIMIT
    assert _repack_outcomes(emitted) == [outcome]
    assert not git_fetcher._repack_git_missing
    [(_, tags)] = _repack_seconds(emitted)
    assert tags == {"outcome": outcome}
    [warning] = [r for r in records if r["level"].name == "WARNING"]
    assert str(exc) in warning["message"]
    # git ran and exited, so it may have deleted packs: release the handle.
    assert path not in GitPolicyFetcher.repos
    assert freed == [path]

    # Within the hour the clone is left alone, fetch after fetch.
    newer = await scope.push_and_sync()
    assert scope.notified[-1][1] == newer
    assert spy.calls == [path]
    assert _repack_outcomes(emitted) == [outcome]

    # The failure is on disk too, for the next process: a new leader starts
    # with an empty _repack_failed_at and must still wait out the hour.
    marker = git_fetcher._repack_failed_marker(scope.clone_path)
    assert marker.exists()
    saved = dict(git_fetcher._repack_failed_at)
    git_fetcher._repack_failed_at.clear()
    await scope.push_and_sync()
    assert spy.calls == [path], "a new process retried within the hour"
    git_fetcher._repack_failed_at.update(saved)

    # Once the hour is up it is tried again.
    git_fetcher._repack_failed_at[scope.source_id] -= (
        git_fetcher._REPACK_FAILURE_COOLDOWN_SECONDS
    )
    # The marker counts from the start of the repack, for the cooldown plus
    # as long as that repack could have run.
    expired = time.time() - (
        git_fetcher._REPACK_FAILURE_COOLDOWN_SECONDS
        + git_fetcher._repack_timeout_seconds()
        + git_fetcher._REPACK_STOP_SECONDS
    )
    os.utime(marker, (expired, expired))
    spy.raises = None
    await scope.push_and_sync()
    assert spy.calls == [path, path]
    assert _count_pack_files(scope.clone_path) == 1
    assert _repack_outcomes(emitted) == [outcome, "ok"]


@pytest.mark.asyncio
async def test_lock_that_cannot_be_taken_fails_the_repack_not_the_sync(
    tmp_path, monkeypatch, emitted, records
):
    """Where flock fails on the clones directory (NFS without
    local_lock=flock), every repack is an error that cools down, and the sync
    still notifies."""
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    _flock_fails_with(monkeypatch, errno.ENOLCK)

    tip = await scope.push_and_sync()  # must not raise

    assert scope.notified[-1][1] == tip
    assert _repack_outcomes(emitted) == ["error"]
    assert scope.source_id in git_fetcher._repack_failed_at
    assert git_fetcher._repack_lock_fds == set()
    assert _count_pack_files(scope.clone_path) == _LIMIT
    [warning] = [r for r in records if r["level"].name == "WARNING"]
    assert "OSError" in warning["message"]


def _fail_repack_setup(monkeypatch, fault: str, clone_path: Path) -> None:
    """Make one of the repack's own steps past the repack lock fail.

    Opening the clone's lock file fails with EACCES, recording the repack
    in it with ENOSPC (a full disk), making the watchdog's pipe with
    EMFILE. Each is patched on the ``os`` module the step calls it
    through, as git_cli_test does for the git command-line ops.
    """
    if fault == "clone lock":
        lock_path = os.fspath(git_cli.clone_lock_path(clone_path))
        real_open = os.open

        def _open(path, flags, mode=0o777, *, dir_fd=None):
            if os.fspath(path) == lock_path:
                raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(git_cli.os, "open", _open)
    elif fault == "record":

        def _full(fd, data, offset):
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

        monkeypatch.setattr(git_cli.os, "pwrite", _full)
    else:

        def _no_pipe():
            raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))

        monkeypatch.setattr(git_fetcher.os, "pipe", _no_pipe)


@pytest.mark.parametrize(
    "fault, errno_",
    [
        ("clone lock", errno.EACCES),
        ("record", errno.ENOSPC),
        ("watchdog pipe", errno.EMFILE),
    ],
    ids=["clone-lock-EACCES", "record-ENOSPC", "pipe-EMFILE"],
)
@pytest.mark.asyncio
async def test_a_repack_whose_own_setup_fails_cools_down_and_frees_both_locks(
    tmp_path, monkeypatch, emitted, records, fault, errno_
):
    """Past the repack lock, the repack opens the clone's lock file, records
    itself in it and makes the watchdog's pipe, and each can fail. The failure
    is the repack's: git never starts, the run is an error that cools down,
    both locks are free with no fd of them left, and the record of an op that
    died before it stays for the next op on the clone.

    Mutation: not dropping the clone's lock or the repack lock on the way
    out, or a record write that empties the lock file before it fails,
    fails it.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()  # the fetch that reaches the limit
    assert set(git_fetcher._repacks_due) == {scope.source_id}
    _record_a_dead_op(scope.clone_path)
    dead_op = _record(scope.clone_path)
    runs = tmp_path / "runs"
    _install_git_shim(tmp_path, monkeypatch, f'echo run >> "{runs}"\n', refs_steps=True)

    with monkeypatch.context() as faults:
        _fail_repack_setup(faults, fault, scope.clone_path)
        await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert not runs.exists()
    assert _repack_outcomes(emitted) == ["error"]
    assert scope.source_id in git_fetcher._repack_failed_at
    assert git_fetcher._repack_lock_fds == set()
    assert _lock_is_free(git_fetcher._repack_lock_dir(scope.clone_path))
    assert _clone_lock_is_free(scope.clone_path)
    assert _record(scope.clone_path) == dead_op
    assert _count_pack_files(scope.clone_path) == _LIMIT
    [warning] = [r for r in records if "failed after" in r["message"]]
    assert os.strerror(errno_) in warning["message"]


def _gut(clone_path: Path) -> None:
    """Remove every object of the clone, its refs left: an invalid clone."""
    objects = clone_path / ".git" / "objects"
    for entry in objects.iterdir():
        if entry.name == "pack":
            for pack in entry.iterdir():
                pack.unlink()
        elif len(entry.name) == 2:
            shutil.rmtree(entry)


@pytest.mark.parametrize("cli", [False, True], ids=["libgit2", "cli"])
@pytest.mark.asyncio
async def test_where_flock_fails_an_invalid_clone_is_cloned_again_with_the_cli_off(
    tmp_path, monkeypatch, records, cli
):
    """Where flock fails (NFS without local_lock=flock), the clone's lock
    cannot be taken. With SCOPES_GIT_FETCH_WITH_CLI off only a repack takes it,
    and no repack runs there, so the invalid clone is deleted without the lock
    and cloned again. With it on every git fetch and clone takes it too and
    fails without it, so the clone is kept: deleted, it could not be cloned
    again.

    Mutation: raising whatever the setting leaves the clone invalid with
    it off (the clone onto its directory fails); deleting whatever the
    setting leaves no clone at all with it on.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.sync()
    GitPolicyFetcher.forget_repo(str(scope.clone_path))
    _gut(scope.clone_path)
    _flock_fails_with(monkeypatch, errno.ENOLCK)

    await scope.sync()

    clone = pygit2.Repository(str(scope.clone_path))
    try:
        assert (clone.get(scope.tip) is None) is cli
    finally:
        clone.free()
    without_lock = [
        r
        for r in records
        if r["level"].name == "WARNING" and "without its lock" in r["message"]
    ]
    assert len(without_lock) == (0 if cli else 1)


def test_failed_repack_prunes_the_expired_cooldowns_of_other_sources(emitted):
    """What keeps the cooldowns bounded as sources come and go: a deleted
    scope's entry is never looked up again, so only the next failure, of
    any clone, removes it once it has expired."""
    now = time.monotonic()
    cooldown = git_fetcher._REPACK_FAILURE_COOLDOWN_SECONDS
    git_fetcher._repack_failed_at.update(
        {"expired": now - cooldown - 1, "cooling": now - 10}
    )
    due = git_fetcher._DueRepack(
        source_id="failing", repo_path="/nonexistent", scope_id="s1", url="u"
    )

    GitPolicyFetcher._on_repack_failed(due, GitRepackError(1, "fatal: x"), 0.5)

    assert set(git_fetcher._repack_failed_at) == {"cooling", "failing"}
    assert _repack_outcomes(emitted) == ["error"]


@pytest.mark.asyncio
async def test_missing_git_is_logged_once_and_then_never_tried_again(
    tmp_path, monkeypatch, emitted, records
):
    """The first due run is the ref steps of the first fresh clone, counted as
    a pack-refs run, not a repack; nothing of the repack runs after it, on any
    clone, at the limit or below it.

    Mutation: counting the ref steps' run as a repack fails the first
    count.
    """
    no_git = tmp_path / "no-git"
    no_git.mkdir()
    monkeypatch.setenv("PATH", str(no_git))  # the real primitives, finding no git
    repack = _RepackSpy()
    pack_refs = _RepackSpy(real=git_fetcher._pack_clone_refs)
    monkeypatch.setattr(git_fetcher, "_repack_clone", repack)
    monkeypatch.setattr(git_fetcher, "_pack_clone_refs", pack_refs)
    first = _ScopeRepo(tmp_path, "s1")
    second = _ScopeRepo(tmp_path, "s2")

    await first.fetched(_LIMIT - 1)

    assert pack_refs.calls == [str(first.clone_path)]
    assert _pack_refs_outcomes(emitted) == ["git_missing"]
    assert _repack_outcomes(emitted) == []
    assert emitted["distribution"] == []  # nothing ran, so no duration
    [error] = [r for r in records if r["level"].name == "ERROR"]
    assert "git" in error["message"]

    await second.fetched(_LIMIT - 1)  # another clone, same process: still off
    tip = await first.push_and_sync()  # at the limit
    await second.push_and_sync()
    assert first.notified[-1][1] == tip
    assert repack.calls == []
    assert pack_refs.calls == [str(first.clone_path)]
    assert _pack_refs_outcomes(emitted) == ["git_missing"]
    assert _repack_outcomes(emitted) == []
    assert [r for r in records if r["level"].name == "ERROR"] == [error]


@pytest.mark.asyncio
async def test_second_repack_is_skipped_while_one_runs_not_queued(
    tmp_path, monkeypatch, emitted
):
    """Waiting would hold the second clone's lock_source, stalling its syncs,
    to buy nothing: the skipped clone just repacks on a later fetch."""
    gate = threading.Event()
    spy = _RepackSpy(gate=gate)
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    first = _ScopeRepo(tmp_path, "s1")
    second = _ScopeRepo(tmp_path, "s2")
    await first.fetched(_LIMIT - 1)
    await second.fetched(_LIMIT - 1)

    first_sync = asyncio.ensure_future(first.push_and_sync())
    try:
        assert await run_sync(spy.started.wait, 5), "first repack never started"
        tip = await asyncio.wait_for(second.push_and_sync(), timeout=5)
        assert second.notified[-1][1] == tip
        assert spy.calls == [str(first.clone_path)]
        assert _count_pack_files(second.clone_path) == _LIMIT
        assert _skips(emitted) == [{"reason": "repack_running"}]
        assert not first_sync.done()
    finally:
        gate.set()
    await asyncio.wait_for(first_sync, timeout=10)
    assert _count_pack_files(first.clone_path) == 1
    assert _repack_outcomes(emitted) == ["ok"]
    assert git_fetcher._repack_failed_at == {}  # a skip is not a failure

    await second.push_and_sync()
    assert spy.calls == [str(first.clone_path), str(second.clone_path)]
    assert _count_pack_files(second.clone_path) == 1


def test_repack_clone_exclusive_returns_none_while_another_holds_the_lock(
    tmp_path, monkeypatch
):
    """The decision is the thread's own non-blocking acquire; the event loop's
    peek at the lock only saves a thread when the answer is obvious."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    assert git_fetcher._repack_lock.acquire(blocking=False)
    try:
        assert git_fetcher._repack_clone_exclusive(_fake_clone(tmp_path), 60) is None
    finally:
        git_fetcher._repack_lock.release()
    assert spy.calls == []


@pytest.mark.asyncio
async def test_repack_outliving_its_awaiter_keeps_the_single_flight_and_the_handle(
    tmp_path, monkeypatch, emitted
):
    """run_in_git_executor stopped waiting but the thread (and git) runs on.

    The sync still completes, the outcome is a timeout with a cooldown,
    a repack of another clone is still refused (the disk bound is about
    git processes, not awaiters), and the cached handle is dropped from
    the cache but never free()'d while its source has a git op in
    flight.
    """
    gate = threading.Event()
    spy = _RepackSpy(gate=gate)  # stuck where no timeout of ours reaches
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    first = _ScopeRepo(tmp_path, "s1")
    second = _ScopeRepo(tmp_path, "s2")
    await first.fetched(_LIMIT - 1)
    await second.fetched(_LIMIT - 1)
    # Only now: the ref steps alone that the setup's syncs ran on the fresh
    # clones are real, and on a loaded machine take more than 0.2 s.
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_TIMEOUT", 0.2)
    monkeypatch.setattr(git_fetcher, "_REPACK_EXECUTOR_SLACK_SECONDS", 0.1)
    path = str(first.clone_path)
    freed = _watch_free(GitPolicyFetcher.repos[path], path)
    try:
        tip = await first.push_and_sync()

        assert first.notified[-1][1] == tip
        assert _repack_outcomes(emitted) == ["timeout"]
        assert first.source_id in git_fetcher._repack_failed_at
        assert git_op_in_flight(first.source_id)
        assert path not in GitPolicyFetcher.repos
        assert freed == []

        await second.push_and_sync()
        assert spy.calls == [path]
        assert _count_pack_files(second.clone_path) == _LIMIT
    finally:
        gate.set()
    assert await run_sync(git_fetcher.drain_git_ops, 10)
    assert freed == []


@pytest.mark.asyncio
async def test_slow_walks_for_the_log_line_never_make_a_repack_a_timeout(
    tmp_path, monkeypatch, emitted, records
):
    """The log line's sizes of the refs and reflogs come from walks of every
    file under refs/ and logs/: 126,000 files on a libgit2 clone of a
    repository with 63,000 branches, slow on a slow volume. They are taken
    outside the git executor's timeout, so a repack that finished in time is an
    "ok" however long they take, and the line still carries them.

    Mutation: walking inside the executor's timeout, as the repack did,
    counts the repack as a timeout and cools the clone down.
    """
    spy = _RepackSpy(real=lambda repo_path, timeout, **kwargs: True)
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_TIMEOUT", 0.2)
    monkeypatch.setattr(git_fetcher, "_REPACK_EXECUTOR_SLACK_SECONDS", 0.1)
    real_walk = git_fetcher._ref_disk_bytes

    def _slow_walk(repo_path):
        time.sleep(0.3)  # each walk alone takes the whole executor timeout
        return real_walk(repo_path)

    monkeypatch.setattr(git_fetcher, "_ref_disk_bytes", _slow_walk)

    await scope.push_and_sync()

    assert spy.calls == [str(scope.clone_path)]
    assert _repack_outcomes(emitted) == ["ok"]
    assert git_fetcher._repack_failed_at == {}
    [done] = [r for r in records if r["message"].startswith("Repacked scope clone")]
    assert done["extra"]["refs_before"] > 0
    assert done["extra"]["refs_after"] > 0
    assert await run_sync(git_fetcher.drain_git_ops, 10)


@pytest.mark.asyncio
async def test_cancelled_sync_propagates_and_single_flight_ends_with_git(
    tmp_path, monkeypatch, emitted
):
    gate = threading.Event()
    spy = _RepackSpy(gate=gate)
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)

    sync = asyncio.ensure_future(scope.push_and_sync())
    try:
        assert await run_sync(spy.started.wait, 5), "repack never started"
        sync.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sync
        assert git_fetcher._repack_lock.locked(), "released while git still runs"
    finally:
        gate.set()
    assert await run_sync(git_fetcher.drain_git_ops, 10)
    assert not git_fetcher._repack_lock.locked()
    assert _repack_outcomes(emitted) == []  # nobody observed an outcome


@pytest.mark.asyncio
async def test_zombie_cap_refusal_is_not_an_attempt_and_arms_no_cooldown(
    tmp_path, monkeypatch, emitted
):
    """Nothing ran and the refusal says nothing about this clone (the cap is
    process-wide backpressure, which is why fetch failures at the cap arm no
    source backoff either), so the next fetch simply tries again."""
    real_run = git_fetcher.run_in_git_executor
    refusals = [GitConcurrencyLimitExceeded("in-flight git ops (40) reached cap")]

    async def _run(func, *args, **kwargs):
        if (
            func is git_fetcher._repack_clone_exclusive
            and refusals
            and _count_pack_files(args[0]) >= _LIMIT
        ):
            raise refusals.pop()
        return await real_run(func, *args, **kwargs)

    monkeypatch.setattr(git_fetcher, "run_in_git_executor", _run)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)

    tip = await scope.push_and_sync()
    assert refusals == []
    assert scope.notified[-1][1] == tip
    assert _count_pack_files(scope.clone_path) == _LIMIT
    assert _repack_outcomes(emitted) == []
    assert git_fetcher._repack_failed_at == {}

    await scope.push_and_sync()
    assert _count_pack_files(scope.clone_path) == 1
    assert _repack_outcomes(emitted) == ["ok"]


@pytest.mark.asyncio
async def test_tip_dropped_by_a_force_push_is_still_readable_after_the_repack(
    tmp_path,
):
    """``-a -d`` without ``-k`` drops what nothing references, and a PDP's diff
    base may be a commit a force-push took off the branch.

    The reflogs keep it, and ``-k`` would keep it without them.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 2)
    base = scope.tip
    old_tip = await scope.push_and_sync()
    assert _count_pack_files(scope.clone_path) == _LIMIT - 1

    new_tip = str(scope.force_push(onto=base))
    await scope.sync_pass()  # force-updates origin/master, then repacks

    assert _count_pack_files(scope.clone_path) == 1
    assert scope.notified[-1][:2] == (old_tip, new_tip)
    reachable = subprocess.run(
        ["git", "-C", str(scope.clone_path), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert old_tip not in reachable  # the premise: only a reflog names it now
    fresh = pygit2.Repository(str(scope.clone_path))
    try:
        assert fresh.get(old_tip) is not None
    finally:
        fresh.free()
    diff = await run_sync(scope.fetcher.make_bundle, old_tip)
    assert (diff.old_hash, diff.hash) == (old_tip, new_tip)


# --- run at the end of the sync pass: ScopesService.sync_scopes ----------------
#
# A fetch that leaves a clone at the limit only marks it due; the pass repacks
# it last, once every notification of the pass is out. Real syncs through the
# service, against an in-memory scope store.


class _FakeScopes:
    """The scope store the service reads, in memory."""

    def __init__(self, *scopes: Scope):
        self.scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id: str) -> Scope:
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]

    async def all(self) -> list:
        return list(self.scopes.values())

    async def delete(self, scope_id: str) -> None:
        self.scopes.pop(scope_id, None)


class _FakePubSub:
    """Records every publish: the notifications PDPs would get."""

    def __init__(self):
        self.published: list = []

    async def publish(self, topics, data=None) -> None:
        self.published.append((list(topics), data))

    def notified(self) -> set:
        """(scope id, new policy hash) of every notification so far."""
        return {
            (topics[0].split(":", 1)[0], data.new_policy_hash)
            for topics, data in self.published
        }


def _scope_on(repo: _ScopeRepo, scope_id: str) -> Scope:
    """A scope on ``repo``'s source (not polled, the source's default)."""
    return Scope(scope_id=scope_id, policy=repo.fetcher._source)


def _service(tmp_path: Path, *scopes: Scope, pubsub=None) -> ScopesService:
    return ScopesService(
        base_dir=tmp_path / "base",
        scopes=_FakeScopes(*scopes),
        pubsub_endpoint=pubsub if pubsub is not None else _FakePubSub(),
    )


def _watcher(service: ScopesService) -> "task_module.ScopesPolicyWatcherTask":
    """The leader's watcher task on ``service``, for its trigger; built without
    __init__, which needs Redis (scopes_task_wiring_test's way)."""
    watcher = task_module.ScopesPolicyWatcherTask.__new__(
        task_module.ScopesPolicyWatcherTask
    )
    watcher._service = service
    return watcher


@pytest.mark.asyncio
async def test_pass_notifies_every_scope_before_it_repacks(tmp_path, monkeypatch):
    """The repack a phase-1 fetch makes due waits for phase 2: the scope that
    shares the clone (and so every phase-2 scope) is notified of the new
    commit before the repack starts, not after it."""
    repo = _ScopeRepo(tmp_path, "s1")
    pubsub = _FakePubSub()
    svc = _service(
        tmp_path, _scope_on(repo, "s1"), _scope_on(repo, "s2"), pubsub=pubsub
    )
    notified_at_start: list = []
    spy = _RepackSpy(on_start=lambda: notified_at_start.append(pubsub.notified()))
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    await svc.sync_scopes()  # the clone: no pack yet
    for _ in range(_LIMIT - 1):
        repo.push()
        await svc.sync_scopes()
    assert _count_pack_files(repo.clone_path) == _LIMIT - 1
    assert spy.calls == []

    tip = str(repo.push())
    await svc.sync_scopes()  # s1's fetch reaches the limit; s2 is phase 2

    assert spy.calls == [str(repo.clone_path)]
    [notified] = notified_at_start
    assert ("s1", tip) in notified
    assert ("s2", tip) in notified, "phase 2 was notified only after the repack"
    assert _count_pack_files(repo.clone_path) == 1
    assert git_fetcher._repacks_due == {}


@pytest.mark.asyncio
async def test_pass_repacks_every_due_clone_one_after_another(
    tmp_path, monkeypatch, emitted
):
    """Run side by side, all repacks but one would find the in-process lock
    held and be skipped; one after another, each clone the pass found due is
    repacked."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    first = _ScopeRepo(tmp_path, "s1")
    second = _ScopeRepo(tmp_path, "s2")
    svc = _service(tmp_path, _scope_on(first, "s1"), _scope_on(second, "s2"))
    await first.fetched(_LIMIT - 1)
    await second.fetched(_LIMIT - 1)
    first.push()
    second.push()

    await svc.sync_scopes()

    assert sorted(spy.calls) == sorted([str(first.clone_path), str(second.clone_path)])
    assert _count_pack_files(first.clone_path) == 1
    assert _count_pack_files(second.clone_path) == 1
    assert _repack_outcomes(emitted) == ["ok", "ok"]
    assert _skips(emitted) == []


@pytest.mark.asyncio
async def test_refresh_repacks_the_clone_it_left_due_with_no_periodic_pass(
    tmp_path, monkeypatch, emitted
):
    """With POLICY_REFRESH_INTERVAL=0, the default, the leader runs one pass,
    at boot, and every later sync is a refresh (POST /scopes/{id}/refresh, a
    PUT) that the watcher's trigger runs on its own.

    So the trigger repacks the clone its sync left due, right after the
    sync, once the refresh's notification is out.
    """
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)
    repo = _ScopeRepo(tmp_path, "s1")
    pubsub = _FakePubSub()
    notified_at_start: list = []
    spy = _RepackSpy(on_start=lambda: notified_at_start.append(pubsub.notified()))
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    watcher = _watcher(_service(tmp_path, _scope_on(repo, "s1"), pubsub=pubsub))
    await repo.fetched(_LIMIT - 1)
    tip = str(repo.push())

    await watcher.trigger(topic=None, data={"scope_id": "s1", "force_fetch": True})

    assert spy.calls == [str(repo.clone_path)]
    [notified] = notified_at_start
    assert ("s1", tip) in notified, "the repack started before the notification"
    assert _count_pack_files(repo.clone_path) == 1
    assert git_fetcher._repacks_due == {}
    assert _repack_outcomes(emitted) == ["ok"]

    # Below the limit again: the next refresh repacks nothing.
    await watcher.trigger(topic=None, data={"scope_id": "s1", "force_fetch": True})
    assert spy.calls == [str(repo.clone_path)]


@pytest.mark.asyncio
async def test_sync_of_one_scope_marks_the_repack_due_and_the_next_pass_runs_it_once(
    tmp_path, monkeypatch, emitted
):
    """ScopesService.sync_scope, the sync of one scope that the watcher's
    trigger runs outside any pass, only marks the clone due: the repack is the
    trigger's next step, or the next pass's.

    The pass repacks it once and clears the mark.
    """
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    repo = _ScopeRepo(tmp_path, "s1")
    svc = _service(tmp_path, _scope_on(repo, "s1"))
    await repo.fetched(_LIMIT - 1)
    tip = str(repo.push())

    await svc.sync_scope(
        scope_id="s1", force_fetch=True, req_time=datetime.datetime.now()
    )

    assert spy.calls == []
    assert _count_pack_files(repo.clone_path) == _LIMIT
    assert set(git_fetcher._repacks_due) == {repo.source_id}
    assert _repack_outcomes(emitted) == []
    assert repo.fetcher.make_bundle().hash == tip  # served before any repack

    await svc.sync_scopes()
    assert spy.calls == [str(repo.clone_path)]
    assert _count_pack_files(repo.clone_path) == 1
    assert git_fetcher._repacks_due == {}
    assert _repack_outcomes(emitted) == ["ok"]

    await svc.sync_scopes()
    assert spy.calls == [str(repo.clone_path)]
    assert _repack_outcomes(emitted) == ["ok"]


@pytest.mark.asyncio
async def test_pass_drops_the_mark_of_a_source_no_scope_uses_any_more(
    tmp_path, monkeypatch, emitted
):
    """The scope whose fetch marked the clone was deleted (or repointed)
    before the pass: the pass drops the mark instead of repacking a clone
    that nothing serves."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    gone = _ScopeRepo(tmp_path, "gone")
    kept = _ScopeRepo(tmp_path, "kept")
    svc = _service(tmp_path, _scope_on(kept, "kept"))  # "gone" is not stored
    await gone.fetched(_LIMIT - 1)
    gone.push()
    await gone.sync()
    assert set(git_fetcher._repacks_due) == {gone.source_id}

    await svc.sync_scopes()

    assert spy.calls == []
    assert git_fetcher._repacks_due == {}
    assert _count_pack_files(gone.clone_path) == _LIMIT
    assert _repack_outcomes(emitted) == []
    assert _skips(emitted) == []


@pytest.mark.parametrize("when", ["marking", "repacking"])
@pytest.mark.asyncio
async def test_unreadable_pack_dir_is_a_warning_not_a_failed_sync(
    tmp_path, monkeypatch, emitted, records, when
):
    """EACCES (or EIO) listing the pack dir, when the fetch marks the clone
    or when the pass would repack it: the sync and the pass complete, PDPs
    hear about the new commit, and the one sign is a WARNING."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    repo = _ScopeRepo(tmp_path, "s1")
    pubsub = _FakePubSub()
    svc = _service(tmp_path, _scope_on(repo, "s1"), pubsub=pubsub)
    await repo.fetched(_LIMIT - 1)
    tip = str(repo.push())
    pack = _pack_dir(repo.clone_path)
    real_scandir = os.scandir

    def _scandir(path="."):
        if Path(path) == pack:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_scandir(path)

    if when == "marking":
        monkeypatch.setattr(os, "scandir", _scandir)
        await svc.sync_scopes()
    else:
        await svc.sync_scope(scope_id="s1", force_fetch=True)  # a refresh marks
        assert set(git_fetcher._repacks_due) == {repo.source_id}
        monkeypatch.setattr(os, "scandir", _scandir)
        await svc.sync_scopes(only_poll_updates=True)  # s1 is not polled

    assert ("s1", tip) in pubsub.notified()
    assert spy.calls == []
    assert git_fetcher._repacks_due == {}
    assert _repack_outcomes(emitted) == []
    assert [r for r in records if r["level"].name == "ERROR"] == []
    [warning] = [r for r in records if r["level"].name == "WARNING"]
    assert warning["message"].startswith("Could not count the packs")
    assert "PermissionError" in warning["message"]


@pytest.mark.parametrize("purge", ["fleet", "delete-floor"])
@pytest.mark.asyncio
async def test_purging_a_source_drops_its_mark(tmp_path, purge):
    """A scope deleted mid-pass is purged before the pass gets to its due
    repack: the purge takes the mark with it, as it does the source's other
    in-memory state, on every worker (the fleet purge) and on the one that
    served the DELETE (its floor)."""
    repo = _ScopeRepo(tmp_path, "s1")
    await repo.fetched(_LIMIT - 1)
    repo.push()
    await repo.sync()
    assert set(git_fetcher._repacks_due) == {repo.source_id}

    if purge == "fleet":
        purge_local_memory(repo.source_id, str(repo.clone_path))
    else:
        await _service(tmp_path)._purge_local_clone_best_effort(
            repo.source_id, repo.clone_path, "s1"
        )
        assert not repo.clone_path.exists()

    assert git_fetcher._repacks_due == {}


async def _run_due_repacks_from(entry: str, source_id: str) -> None:
    """The due repack of ``source_id``, run the way a pass ends or the way the
    watcher's trigger ends a refresh."""
    if entry == "pass":
        await GitPolicyFetcher.run_due_repacks({source_id})
    else:
        await GitPolicyFetcher.run_due_repack(source_id, wait_for_lock=True)


@pytest.mark.asyncio
async def test_source_purged_during_an_earlier_repack_of_the_pass_gets_no_lock(
    tmp_path, monkeypatch
):
    """A scope deleted while the pass repacks another clone is purged, with its
    mark and its clone's lock.

    The pass, which listed the marks when it started, then skips that
    source without minting it a lock: nothing would remove one (invariant
    I4 of the git-leak bed).
    """
    gate = threading.Event()
    spy = _RepackSpy(gate=gate)
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    first = _ScopeRepo(tmp_path, "a")
    gone = _ScopeRepo(tmp_path, "gone")
    for repo in (first, gone):
        await repo.fetched(_LIMIT - 1)
    for repo in (first, gone):
        repo.push()
        await repo.sync()  # marks due
    assert list(git_fetcher._repacks_due) == [first.source_id, gone.source_id]

    run = asyncio.ensure_future(
        GitPolicyFetcher.run_due_repacks({first.source_id, gone.source_id})
    )
    try:
        assert await run_sync(spy.started.wait, 5), "the first repack never started"
        # The fleet purge, as handle_purge_message runs it.
        async with GitPolicyFetcher.lock_source(gone.source_id):
            purge_local_memory(gone.source_id, str(gone.clone_path))
            GitPolicyFetcher.repo_locks.pop(gone.source_id, None)
    finally:
        gate.set()
    await asyncio.wait_for(run, 30)

    assert spy.calls == [str(first.clone_path)]
    assert git_fetcher._repacks_due == {}
    assert gone.source_id not in GitPolicyFetcher.repo_locks, "stray lock minted"


@pytest.mark.parametrize("purge", ["fleet", "delete-floor", "floor-cannot-read"])
@pytest.mark.asyncio
async def test_purge_the_refresh_waited_behind_leaves_it_nothing_to_do(
    tmp_path, monkeypatch, purge
):
    """A purge of the clone's source holds its lock_source, and the refresh's
    repack queues behind it.

    Every purge takes the lock away (it pops the entry while it holds
    it), so the repack gives up rather than retry on a fresh lock: it
    repacks nothing and mints no lock to outlive the source. Where the
    purge dropped the mark, nothing is left. Where it kept the clone and
    the mark (the delete floor when it cannot read the store), the mark
    stays for a later pass, which is why the repack takes the mark only
    under the lock.
    """
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    repo = _ScopeRepo(tmp_path, "s1")
    await repo.fetched(_LIMIT - 1)
    repo.push()
    await repo.sync()  # marks due
    sid = repo.source_id
    svc = _service(tmp_path)  # the deleted scope is no longer stored
    # The floor parks in its store read until this is set. Ungated, a read that
    # fails at once ends the floor in the tick that starts it:
    # asyncio.wait_for runs the read in the floor's own task.
    read_gate = asyncio.Event()
    read_store = svc._scopes.all

    async def _gated_read() -> list:
        await read_gate.wait()
        if purge == "floor-cannot-read":
            raise ConnectionError("scope store unreachable")
        return await read_store()

    monkeypatch.setattr(svc._scopes, "all", _gated_read)

    if purge == "fleet":
        async with GitPolicyFetcher.lock_source(sid):
            repack = asyncio.ensure_future(
                GitPolicyFetcher.run_due_repack(sid, wait_for_lock=True)
            )
            await asyncio.sleep(0)  # it queues behind the purge
            # handle_purge_message's critical section.
            purge_local_memory(sid, str(repo.clone_path))
            GitPolicyFetcher.repo_locks.pop(sid, None)
    else:
        floor = asyncio.ensure_future(
            svc._purge_local_clone_best_effort(sid, repo.clone_path, "s1")
        )
        await asyncio.sleep(0)  # it takes the lock and parks in the store read
        lock = GitPolicyFetcher.repo_locks[sid]
        assert lock.locked()
        repack = asyncio.ensure_future(
            GitPolicyFetcher.run_due_repack(sid, wait_for_lock=True)
        )
        await asyncio.sleep(0)  # it queues behind the floor
        assert len(lock._waiters or ()) == 1, "the repack is not queued"
        read_gate.set()
        await asyncio.wait_for(floor, 10)
    await asyncio.wait_for(repack, 10)

    assert spy.calls == []
    assert sid not in GitPolicyFetcher.repo_locks, "stray lock minted"
    if purge == "floor-cannot-read":
        assert set(git_fetcher._repacks_due) == {sid}
        assert repo.clone_path.exists()
    else:
        assert git_fetcher._repacks_due == {}


@pytest.mark.parametrize("entry", ["pass", "refresh"])
@pytest.mark.asyncio
async def test_due_repack_waits_out_a_git_op_of_the_clone_that_outlived_its_awaiter(
    tmp_path, monkeypatch, emitted, entry
):
    """A later fetch of a clone already marked due timed out, and its thread
    runs on through the clone's cached handle.

    The pass (or the refresh) skips that clone's repack and keeps the
    mark. Run beside the fetch, the repack would rewrite the packs the
    fetch reads, clear its busy marker (so the next sync would fetch
    beside it as well) and free() the handle it uses. Once the fetch is
    gone, the next one repacks the clone.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()  # reaches the limit: marked due
    assert set(git_fetcher._repacks_due) == {scope.source_id}
    path = str(scope.clone_path)
    handle = GitPolicyFetcher.repos[path]
    freed = _watch_free(handle, path)

    gate = threading.Event()
    in_fetch = threading.Event()

    def _hung_fetch(self, *args, **kwargs):
        in_fetch.set()
        gate.wait(30)  # then returns without touching the handle again

    monkeypatch.setattr(pygit2.remotes.Remote, "fetch", _hung_fetch)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.3)
    scope.push()
    try:
        await scope.sync()  # stops waiting for the fetch after 0.3 s
        assert in_fetch.is_set()
        assert git_op_in_flight(scope.source_id)

        await _run_due_repacks_from(entry, scope.source_id)

        assert _repack_outcomes(emitted) == []
        assert _skips(emitted) == []  # not another repack running: not counted
        assert set(git_fetcher._repacks_due) == {scope.source_id}
        assert git_op_in_flight(scope.source_id), "the fetch's busy marker is gone"
        assert GitPolicyFetcher.repos.get(path) is handle
        assert freed == [], "the handle the fetch thread uses was free()'d"
    finally:
        gate.set()
    assert await run_sync(git_fetcher.drain_git_ops, 10)

    await _run_due_repacks_from(entry, scope.source_id)
    assert _repack_outcomes(emitted) == ["ok"]
    assert _count_pack_files(scope.clone_path) == 1
    assert git_fetcher._repacks_due == {}


@pytest.mark.asyncio
async def test_pass_never_waits_on_a_due_clone_another_sync_holds(
    tmp_path, monkeypatch
):
    """A refresh of a scope the periodic pass does not poll marked its clone
    due, and a second refresh of it hangs in its fetch with
    SCOPES_GIT_FETCH_TIMEOUT=0 (no limit), holding the clone's lock_source.

    The pass needs no lock of that clone to end, so it skips the repack
    and keeps the mark instead of waiting: waiting, it would never end,
    and neither would the periodic polling or the leader heartbeat. The
    next pass after the refresh repacks the clone.
    """
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    unpolled = _ScopeRepo(tmp_path, "unpolled")  # poll_updates=False
    polled = _ScopeRepo(tmp_path, "polled")
    polled.fetcher._source.poll_updates = True
    pubsub = _FakePubSub()
    svc = _service(
        tmp_path,
        _scope_on(unpolled, "unpolled"),
        _scope_on(polled, "polled"),
        pubsub=pubsub,
    )
    await unpolled.fetched(_LIMIT - 1)
    await polled.fetched(1)
    unpolled.push()
    await svc.sync_scope(scope_id="unpolled", force_fetch=True)  # marks due
    assert set(git_fetcher._repacks_due) == {unpolled.source_id}

    gate = threading.Event()
    in_fetch = threading.Event()
    real_fetch = pygit2.remotes.Remote.fetch

    def _hung_fetch(self, *args, **kwargs):
        in_fetch.set()
        gate.wait(30)
        return real_fetch(self, *args, **kwargs)

    monkeypatch.setattr(pygit2.remotes.Remote, "fetch", _hung_fetch)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0)
    unpolled.push()
    hung = asyncio.ensure_future(svc.sync_scope(scope_id="unpolled", force_fetch=True))
    try:
        assert await run_sync(in_fetch.wait, 5), "the second refresh never fetched"
        monkeypatch.setattr(pygit2.remotes.Remote, "fetch", real_fetch)
        tip = str(polled.push())

        periodic = asyncio.ensure_future(svc.sync_scopes(only_poll_updates=True))
        done, _ = await asyncio.wait({periodic}, timeout=10)

        assert done, "the pass waited on the lock of a clone it does not need"
        periodic.result()
        assert ("polled", tip) in pubsub.notified()
        assert spy.calls == []
        assert set(git_fetcher._repacks_due) == {unpolled.source_id}
        assert not hung.done()
    finally:
        gate.set()
    await asyncio.wait_for(hung, 10)

    await svc.sync_scopes(only_poll_updates=True)
    assert spy.calls == [str(unpolled.clone_path)]
    assert git_fetcher._repacks_due == {}


@pytest.mark.asyncio
async def test_pass_never_queues_behind_a_sync_woken_for_the_clone_lock(
    tmp_path, monkeypatch
):
    """Between a release of the clone's lock_source and the queued sync it
    wakes taking it, the lock reads as free, yet an acquire then would queue
    behind that sync's whole hold.

    The pass counts a queued task as using the lock too, and skips.
    """
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()  # marks due
    sid = scope.source_id
    queued_in = asyncio.Event()
    queued_gate = asyncio.Event()

    async def _queued_sync():
        async with GitPolicyFetcher.lock_source(sid):
            queued_in.set()
            await queued_gate.wait()

    # A bound for a pass that does queue, so the test fails instead of hanging.
    unstick = asyncio.get_running_loop().call_later(5, queued_gate.set)
    try:
        async with GitPolicyFetcher.lock_source(sid):
            queued = asyncio.ensure_future(_queued_sync())
            await asyncio.sleep(0)  # it queues for the lock
        # Released: the queued sync is woken but has not taken the lock, and
        # this task goes on without yielding to it.
        assert not GitPolicyFetcher.repo_locks[sid].locked()
        assert not queued_in.is_set()

        await GitPolicyFetcher.run_due_repacks({sid})

        assert not queued_gate.is_set(), "the pass queued behind the woken sync"
        assert spy.calls == []
        assert set(git_fetcher._repacks_due) == {sid}
    finally:
        unstick.cancel()
        queued_gate.set()
    await asyncio.wait_for(queued, 5)
    assert queued_in.is_set()


@pytest.mark.asyncio
async def test_refresh_waits_for_the_clone_lock_its_repack_needs(tmp_path, monkeypatch):
    """Unlike a pass, the refresh's repack waits for the clone's lock_source,
    as the refresh's own sync just did: nothing waits on the watcher's trigger,
    and on a clone whose lock is never free at the end of a pass (the busiest
    one, refreshed back to back) skipping would starve the repack for good.

    Here another sync of the clone queues for its lock during the
    refresh's fetch: the refresh repacks once that sync is done.
    """
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    repo = _ScopeRepo(tmp_path, "s1")
    svc = _service(tmp_path, _scope_on(repo, "s1"))
    watcher = _watcher(svc)
    await repo.fetched(_LIMIT - 1)
    repo.push()
    gate = threading.Event()
    in_fetch = threading.Event()
    real_fetch = pygit2.remotes.Remote.fetch

    def _slow_fetch(self, *args, **kwargs):
        in_fetch.set()
        gate.wait(10)
        return real_fetch(self, *args, **kwargs)

    monkeypatch.setattr(pygit2.remotes.Remote, "fetch", _slow_fetch)
    refresh = asyncio.ensure_future(
        watcher.trigger(topic=None, data={"scope_id": "s1", "force_fetch": True})
    )
    try:
        assert await run_sync(in_fetch.wait, 5), "the refresh never fetched"
        other = asyncio.ensure_future(svc.sync_scope(scope_id="s1"))
        await asyncio.sleep(0)
        lock = GitPolicyFetcher.repo_locks[repo.source_id]
        assert len(lock._waiters or ()) == 1, "the other sync is not queued"
    finally:
        gate.set()
    await asyncio.wait_for(asyncio.gather(refresh, other), 10)

    assert spy.calls == [str(repo.clone_path)]
    assert _count_pack_files(repo.clone_path) == 1
    assert git_fetcher._repacks_due == {}


def test_preload_marks_the_repack_due_and_the_first_pass_runs_it(
    tmp_path, monkeypatch, no_redis
):
    """The preload runs in the gunicorn master before any worker starts, so a
    repack there would hold up every worker.

    It only marks the clone; the mark is inherited by the forked leader,
    whose first pass repacks it even when that pass fetches nothing
    (here: a periodic pass, and the scope is not polled).
    """
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    repo = _ScopeRepo(tmp_path, "s1")
    scopes = _FakeScopes(_scope_on(repo, "s1"))
    asyncio.run(repo.fetched(_LIMIT - 1))
    repo.push()
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path / "base"))
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: scopes)
    # Both would replace this test's log sinks and metrics client.
    monkeypatch.setattr(task_module, "configure_logs", lambda: None)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)

    task_module.ScopesPolicyWatcherTask.preload_scopes()

    assert spy.calls == []
    assert _count_pack_files(repo.clone_path) == _LIMIT
    assert set(git_fetcher._repacks_due) == {repo.source_id}

    leader = ScopesService(
        base_dir=tmp_path / "base", scopes=scopes, pubsub_endpoint=_FakePubSub()
    )
    asyncio.run(leader.sync_scopes(only_poll_updates=True))
    assert spy.calls == [str(repo.clone_path)]
    assert _count_pack_files(repo.clone_path) == 1
    assert git_fetcher._repacks_due == {}


class _LoopKey:
    """A weakly referenceable key, as the event loops keying
    _live_ops_semaphores are."""


def test_forked_child_starts_with_the_single_flight_free(tmp_path, monkeypatch):
    """A repack thread running in the parent at fork does not exist in the
    child, so nothing there could release the lock it inherited held.

    The fork handler runs here, in the test process, so every global it
    resets is swapped for a stand-in first: what the rest of the process
    holds across it (a busy marker, the real single-flight lock) is left
    alone.
    """
    held = git_fetcher._repack_lock
    assert held.acquire(blocking=False)
    git_fetcher._git_busy.add("held-across-the-handler")
    busy_lock = threading.Lock()
    busy_lock.acquire()  # the 'before' fork handler holds it across fork
    loop = _LoopKey()  # held here, so its entry outlives the setup
    semaphores: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary({loop: object()})
    lock_fd = os.open(tmp_path, os.O_RDONLY)
    lock_fds = {lock_fd}
    try:
        with monkeypatch.context() as m:
            m.setattr(git_fetcher, "_git_busy_lock", busy_lock)
            m.setattr(git_fetcher, "_live_ops_semaphores", semaphores)
            m.setattr(git_fetcher, "_git_busy", {"a stale marker"})
            m.setattr(git_fetcher, "_repack_lock_fds", lock_fds)
            m.setattr(git_fetcher, "_repack_lock", held)

            git_fetcher._reset_git_executor_after_fork()

            assert git_fetcher._repack_lock is not held
            assert not git_fetcher._repack_lock.locked()
            assert not busy_lock.locked()
            assert len(semaphores) == 0, "the live-op semaphores were kept"
            assert git_fetcher._git_busy == set()
            assert lock_fds == set()
            with pytest.raises(OSError):
                os.fstat(lock_fd)
        assert git_fetcher._repack_lock is held and held.locked()
        assert "held-across-the-handler" in git_fetcher._git_busy
    finally:
        git_fetcher._git_busy.discard("held-across-the-handler")
        if held.locked():
            held.release()
        # Only if the handler did not: the number of an fd it closed may
        # belong to another open file by now.
        if lock_fd in lock_fds:
            os.close(lock_fd)


# --- GitPython handles on scope clones are closed ------------------------------
#
# An open git.Repo keeps persistent `git cat-file --batch(-check)` processes,
# which map every pack they read and keep a pack a repack deleted allocated
# on disk. Unclosed, they live until the garbage collector breaks the Repo's
# reference cycle.

_REAL_GIT_REPO = git.Repo


class _ClosingRecorder(_REAL_GIT_REPO):
    """git.Repo that records its instances, and on close() which of the
    persistent cat-file processes it had were gone once it returned."""

    opened: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reaped = None
        _ClosingRecorder.opened.append(self)

    def close(self):
        procs = [
            cmd.proc
            for cmd in (self.git.cat_file_all, self.git.cat_file_header)
            if cmd is not None and getattr(cmd, "proc", None) is not None
        ]
        super().close()
        self.reaped = [proc.poll() is not None for proc in procs]


@pytest.fixture
def recorded_repos(monkeypatch):
    _ClosingRecorder.opened = []
    monkeypatch.setattr(git_fetcher, "Repo", _ClosingRecorder)
    monkeypatch.setattr(git, "Repo", _ClosingRecorder)  # scopes/service's git.Repo
    return _ClosingRecorder.opened


def _assert_closed_with_cat_file_gone(repos: list, count: int) -> None:
    assert len(repos) == count
    for repo in repos:
        assert repo.reaped is not None, "the Repo was never closed"
        assert repo.reaped, "the premise: reading commits started cat-file"
        assert all(repo.reaped), "a cat-file process outlived close()"


@pytest.mark.asyncio
async def test_make_bundle_closes_its_repo(tmp_path, recorded_repos):
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(1)
    base, head = (str(c) for c in (scope.notified[0][1], scope.tip))

    full = scope.fetcher.make_bundle()
    diff = scope.fetcher.make_bundle(base)

    assert full.hash == head
    assert (diff.old_hash, diff.hash) == (base, head)
    _assert_closed_with_cat_file_gone(recorded_repos, 2)


@pytest.mark.asyncio
async def test_new_commits_callback_closes_its_repo(tmp_path, recorded_repos):
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(1)
    base, head = (str(c) for c in (scope.notified[0][1], scope.tip))
    callbacks = NewCommitsCallbacks(
        base_dir=tmp_path / "base",
        scope_id="s1",
        source=scope.fetcher._source,
        pubsub_endpoint=None,
    )
    published = []

    async def _publish(notification):
        published.append(notification)

    callbacks.trigger_notification = _publish

    await callbacks.on_update(base, head)

    [notification] = published
    assert notification.update.new_policy_hash == head
    assert notification.update.old_policy_hash == base
    _assert_closed_with_cat_file_gone(recorded_repos, 1)


# --- review follow-ups --------------------------------------------------------


def test_pack_a_fetch_lands_while_git_runs_is_not_an_incomplete_repack(
    tmp_path, monkeypatch
):
    """A fetch in another process can install a pack after git listed the packs
    it replaces.

    Only packs older than the repack count, so the new pack plus that
    one is a complete repack, not a failure and an hour's cooldown.
    """
    clone_path = _fake_clone(tmp_path)
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'pack="$2/.git/objects/pack"\n'
        'rm -f "$pack/pack-aaaa.pack" "$pack/pack-aaaa.idx"\n'
        ': > "$pack/pack-bbbb.pack"\n: > "$pack/pack-bbbb.idx"\n'  # git's own
        ': > "$pack/pack-dddd.pack"\n: > "$pack/pack-dddd.idx"\n',  # a fetch's
    )

    assert _repack_clone(clone_path, timeout=60) is True
    assert _count_pack_files(clone_path) == 2


def test_repack_argv_raises_its_own_oom_score_where_linux_has_one(monkeypatch):
    """Git starts through sh, with the git command-line fetch's watchdog; on
    Linux sh first raises its oom_score_adj, which git inherits."""
    real_exists = os.path.exists
    monkeypatch.setattr(
        git_fetcher.os.path,
        "exists",
        lambda p: True if p == git_fetcher._OOM_SCORE_ADJ_PATH else real_exists(p),
    )
    argv = git_fetcher._repack_argv("/usr/bin/git", "/clones/x")
    assert argv[:2] == ["/bin/sh", "-c"]
    assert argv[2].startswith("{ echo 1000 > /proc/self/oom_score_adj; }")
    assert git_cli.WATCHDOG_SCRIPT in argv[2]
    assert argv[2].endswith('exit "$s"')
    assert argv[3:6] == ["sh", "/usr/bin/git", "-C"]

    monkeypatch.setattr(git_fetcher.os.path, "exists", lambda p: False)
    argv = git_fetcher._repack_argv("/usr/bin/git", "/clones/x")
    assert argv[:2] == ["/bin/sh", "-c"]
    assert "oom_score_adj" not in argv[2]
    assert argv[2].startswith(git_cli.WATCHDOG_SCRIPT)


@pytest.mark.skipif(not os.path.exists("/proc/self/oom_score_adj"), reason="Linux only")
def test_git_runs_with_a_raised_oom_score(tmp_path, monkeypatch):
    clone_path = _fake_clone(tmp_path)
    out = tmp_path / "oom"
    _install_git_shim(
        tmp_path, monkeypatch, f'cat /proc/self/oom_score_adj > "{out}"\n'
    )
    _repack_clone(clone_path, timeout=60)
    assert out.read_text().strip() == str(git_fetcher._REPACK_OOM_SCORE_ADJ)


def test_index_seen_without_its_pack_for_a_minute_is_swept_with_companions(tmp_path):
    """Git deletes an old pack's .pack before its .idx, so a repack killed mid-
    delete leaves the .idx for good.

    A sweep that finds it orphaned a minute after an earlier sweep did
    removes it, with its companions.
    """
    pack = tmp_path / "pack"
    pack.mkdir()
    for name in ("pack-old1.idx", "pack-old1.rev", "pack-live.pack", "pack-live.idx"):
        (pack / name).write_bytes(b"x")

    git_fetcher._remove_repack_leftovers(pack, "test")  # first sighting: stays
    assert "pack-old1.idx" in os.listdir(pack)

    path = os.fspath(pack / "pack-old1.idx")
    git_fetcher._orphan_index_first_seen[path] -= (
        git_fetcher._ORPHAN_INDEX_MIN_AGE_SECONDS
    )
    git_fetcher._remove_repack_leftovers(pack, "test")

    assert sorted(os.listdir(pack)) == ["pack-live.idx", "pack-live.pack"]
    assert path not in git_fetcher._orphan_index_first_seen


def test_index_whose_pack_arrives_or_is_kept_stays(tmp_path):
    """One sighting is libgit2 between committing the .idx and renaming the
    .pack in: once the .pack is there the .idx is forgotten.

    A .keep asks to keep the pack.
    """
    pack = tmp_path / "pack"
    pack.mkdir()
    for name in ("pack-young.idx", "pack-kept.idx", "pack-kept.keep"):
        (pack / name).write_bytes(b"x")
    git_fetcher._remove_repack_leftovers(pack, "test")
    (pack / "pack-young.pack").write_bytes(b"x")  # the rename landed
    for path in list(git_fetcher._orphan_index_first_seen):
        git_fetcher._orphan_index_first_seen[path] -= 3600
    git_fetcher._remove_repack_leftovers(pack, "test")

    assert sorted(os.listdir(pack)) == [
        "pack-kept.idx",
        "pack-kept.keep",
        "pack-young.idx",
        "pack-young.pack",
    ]
    assert git_fetcher._orphan_index_first_seen == {}


def test_no_sweep_while_git_outlives_its_sigkill(tmp_path, monkeypatch):
    """A git stuck past the SIGKILL wait may still be renaming files in the
    pack dir, so nothing is swept then: the next repack sweeps.

    Only git repack reports as stuck, and its timeout leaves the ref steps
    before it room on a loaded machine: a ref step stopped as stuck at its
    share of the timeout ends the repack before git repack starts.
    """
    clone_path = _fake_clone(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'pack="$2/.git/objects/pack"\n: > "$pack/tmp_pack_live"\n'
        f': > "{state}/ready"\nexec sleep 30\n',
    )
    real_stop = git_fetcher._stop_repack

    def _stuck(proc, grace, what):
        real_stop(proc, 0.0)  # really stop it, then report git repack stuck
        return "repack" not in proc.args

    monkeypatch.setattr(git_fetcher, "_stop_repack", _stuck)
    # The leftover of an earlier dead repack is swept before git starts. 8 s:
    # the ref steps and then the shim start within it on a loaded machine.
    with pytest.raises(TimeoutError, match="during git repack"):
        _repack_clone(clone_path, timeout=8)
    assert (state / "ready").exists(), "git repack never ran; test proves nothing"
    assert _git_temp_names(clone_path) == ["tmp_pack_live"]


@pytest.mark.parametrize(
    "configured, expected", [(0, 0), (-3, 0), (1, 2), (2, 2), (50, 50)]
)
def test_pack_limit_of_one_counts_as_two(monkeypatch, records, configured, expected):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", configured)
    assert git_fetcher._repack_pack_limit() == expected
    assert git_fetcher._repack_pack_limit() == expected
    warnings = [r for r in records if r["level"].name == "WARNING"]
    assert len(warnings) == (1 if configured == 1 else 0)


@pytest.mark.asyncio
async def test_no_repack_starts_while_a_sync_pass_runs(tmp_path, monkeypatch, emitted):
    """A pass takes a semaphore slot before it waits for a clone's lock, so a
    repack running beside it would fill every slot with waiters for that clone
    and stall the whole pass.

    The mark stays, and each deferral is counted; the pass repacks it at
    its end.
    """
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()  # marks it due
    assert scope.source_id in git_fetcher._repacks_due

    with GitPolicyFetcher.sync_pass():
        await GitPolicyFetcher.run_due_repack(scope.source_id, wait_for_lock=True)
        await GitPolicyFetcher.run_due_repacks({scope.source_id})
    assert spy.calls == []
    assert scope.source_id in git_fetcher._repacks_due
    assert git_fetcher._sync_passes_in_flight == 0
    assert _skips(emitted) == [{"reason": "pass_in_flight"}] * 2

    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    assert spy.calls == [str(scope.clone_path)]
    assert _count_pack_files(scope.clone_path) == 1


@pytest.mark.asyncio
async def test_a_pass_counts_as_in_flight_only_until_its_own_repacks(
    tmp_path, monkeypatch
):
    """sync_scopes is in flight through both phases and out of it for the
    repacks it ends with, so its own repacks run."""
    repo = _ScopeRepo(tmp_path, "s1")
    svc = _service(tmp_path, _scope_on(repo, "s1"))
    seen: list = []
    real = svc._sync_scopes_concurrently

    async def _spy(*args, **kwargs):
        seen.append(("phase", git_fetcher._sync_passes_in_flight))
        return await real(*args, **kwargs)

    async def _repacks(live):
        seen.append(("repacks", git_fetcher._sync_passes_in_flight))

    monkeypatch.setattr(svc, "_sync_scopes_concurrently", _spy)
    monkeypatch.setattr(GitPolicyFetcher, "run_due_repacks", staticmethod(_repacks))
    await svc.sync_scopes()
    assert seen == [("phase", 1), ("phase", 1), ("repacks", 0)]


@pytest.mark.asyncio
async def test_repack_skipped_for_a_running_repack_keeps_its_mark(
    tmp_path, monkeypatch, emitted
):
    """The mark is taken right before the repack; a repack that cannot start
    because another one runs puts it back, for the next pass or refresh."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()
    assert git_fetcher._repack_lock.acquire(blocking=False)
    try:
        await GitPolicyFetcher.run_due_repacks({scope.source_id})
    finally:
        git_fetcher._repack_lock.release()
    assert spy.calls == []
    assert _skips(emitted) == [{"reason": "repack_running"}]
    assert scope.source_id in git_fetcher._repacks_due

    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    assert spy.calls == [str(scope.clone_path)]


def test_keep_due_never_revives_the_mark_of_a_purged_source():
    """A purge unmaps the clone's lock and drops the mark; a repack still
    holding the old lock must not put the mark back."""
    due = git_fetcher._DueRepack(
        source_id="src", repo_path="/clones/src", scope_id="s", url="u"
    )
    held = asyncio.Lock()
    GitPolicyFetcher.repo_locks["src"] = held
    GitPolicyFetcher._keep_due(due, held)
    assert git_fetcher._repacks_due == {"src": due}

    git_fetcher._repacks_due.clear()
    GitPolicyFetcher.repo_locks["src"] = asyncio.Lock()  # a purge re-minted it
    GitPolicyFetcher._keep_due(due, held)
    assert git_fetcher._repacks_due == {}
    GitPolicyFetcher.repo_locks.pop("src", None)


@pytest.mark.asyncio
async def test_remove_clone_dir_exclusive_removes_under_the_repack_lock(tmp_path):
    clones = tmp_path / "git_sources"
    clone = clones / "src"
    (clone / ".git").mkdir(parents=True)
    assert await git_fetcher.remove_clone_dir_exclusive(str(clone)) is True
    assert not clone.exists()
    assert _lock_is_free(clones)


@pytest.mark.asyncio
async def test_remove_clone_dir_exclusive_waits_for_a_running_repack(
    tmp_path, monkeypatch
):
    """The DELETE floor runs on any worker, not under the repacking leader's
    lock_source: it waits for the repack lock, bounded, and leaves the dir
    if a repack still holds it then."""
    monkeypatch.setattr(git_fetcher, "_repack_timeout_seconds", lambda: 0.2)
    monkeypatch.setattr(git_fetcher, "_REPACK_STOP_SECONDS", 0.2)
    clones = tmp_path / "git_sources"
    clone = clones / "src"
    (clone / ".git").mkdir(parents=True)
    held = _hold_lock(clones)
    try:
        assert await git_fetcher.remove_clone_dir_exclusive(str(clone)) is False
        assert clone.exists()
    finally:
        os.close(held)
    assert await git_fetcher.remove_clone_dir_exclusive(str(clone)) is True
    assert not clone.exists()


@pytest.mark.parametrize("cli", [False, True], ids=["libgit2", "cli"])
@pytest.mark.asyncio
async def test_remove_clone_dir_exclusive_where_flock_fails(tmp_path, monkeypatch, cli):
    """The DELETE floor where no lock can be taken (NFS without
    local_lock=flock): the clone is removed without them with
    SCOPES_GIT_FETCH_WITH_CLI off, as for invalid-repo recovery, and kept, the
    error raised, with it on.

    Mutation: raising whatever the setting leaves a deleted scope's
    clone on disk.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    clones = tmp_path / "git_sources"
    clone = clones / "src"
    (clone / ".git").mkdir(parents=True)
    _flock_fails_with(monkeypatch, errno.ENOLCK)

    if cli:
        with pytest.raises(OSError) as info:
            await git_fetcher.remove_clone_dir_exclusive(str(clone))
        assert info.value.errno == errno.ENOLCK
        assert clone.exists()
    else:
        assert await git_fetcher.remove_clone_dir_exclusive(str(clone)) is True
        assert not clone.exists()
    assert git_fetcher._repack_lock_fds == set()


@pytest.mark.asyncio
async def test_refresh_that_waited_for_the_lock_defers_to_a_pass_started_meanwhile(
    tmp_path, monkeypatch
):
    """The pass check runs again once the lock is held: a refresh's wait for
    the clone's lock can outlast the start of a pass."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()
    lock = GitPolicyFetcher.repo_locks.setdefault(scope.source_id, asyncio.Lock())
    await lock.acquire()
    refresh = asyncio.ensure_future(
        GitPolicyFetcher.run_due_repack(scope.source_id, wait_for_lock=True)
    )
    assert await _wait_for_async(lambda: _lock_has_waiter(lock))
    with GitPolicyFetcher.sync_pass():
        lock.release()
        await asyncio.wait_for(refresh, timeout=10)
    assert spy.calls == []
    assert scope.source_id in git_fetcher._repacks_due


def _lock_has_waiter(lock: asyncio.Lock) -> bool:
    return any(not w.cancelled() for w in (getattr(lock, "_waiters", None) or ()))


async def _wait_for_async(condition, deadline_seconds: float = 10.0) -> bool:
    async def _poll():
        while not condition():
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(_poll(), timeout=deadline_seconds)
    except asyncio.TimeoutError:
        return False
    return True


@pytest.mark.asyncio
async def test_repack_blocked_by_another_process_or_the_zombie_cap_keeps_its_mark(
    tmp_path, monkeypatch, emitted
):
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()

    # Another process holds the pod-wide lock: _repack_clone returns False.
    clones_dir = git_fetcher._repack_lock_dir(scope.clone_path)
    held = _hold_lock(clones_dir)
    try:
        await GitPolicyFetcher.run_due_repacks({scope.source_id})
    finally:
        os.close(held)
    assert scope.source_id in git_fetcher._repacks_due
    assert _skips(emitted) == [{"reason": "repack_running"}]

    # The git executor refuses work at the zombie cap.
    real_run = git_fetcher.run_in_git_executor

    async def _refuse(func, *args, **kwargs):
        if func is git_fetcher._repack_clone_exclusive:
            raise GitConcurrencyLimitExceeded("cap reached")
        return await real_run(func, *args, **kwargs)

    monkeypatch.setattr(git_fetcher, "run_in_git_executor", _refuse)
    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    assert scope.source_id in git_fetcher._repacks_due
    assert _repack_outcomes(emitted) == []
    assert _count_pack_files(scope.clone_path) == _LIMIT


@pytest.mark.asyncio
async def test_repack_of_a_clone_a_git_op_holds_is_a_clone_busy_skip(tmp_path, emitted):
    """A git command-line op of another process holds the clone's own lock: the
    repack is skipped as a busy clone, not as a repack running elsewhere, and
    neither fails nor cools down; the mark stays for when the lock is free."""
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()
    emitted["increment"].clear()

    held = git_cli.take_clone_lock(scope.clone_path)
    assert held is not None
    try:
        with capture_records() as records:
            await GitPolicyFetcher.run_due_repacks({scope.source_id})
    finally:
        git_cli.drop_clone_lock(held)
    assert scope.source_id in git_fetcher._repacks_due
    assert _skips(emitted) == [{"reason": "clone_busy"}]
    assert _repack_outcomes(emitted) == []
    assert [
        r["level"].name
        for r in records.emitted
        if "a git op holds the clone's lock" in r["message"]
    ] == ["DEBUG"]

    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    assert _count_pack_files(scope.clone_path) == 1


@pytest.mark.asyncio
async def test_mark_made_before_a_failure_elsewhere_waits_out_the_marker(
    tmp_path, monkeypatch
):
    """A clone marked due before another process's repack of it failed is
    still left alone for the hour: the due repack reads the marker too."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()
    assert scope.source_id in git_fetcher._repacks_due
    git_fetcher._record_repack_failure(scope.clone_path)

    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    assert spy.calls == []


def test_attempt_marker_is_there_while_git_runs_and_gone_after_success(
    tmp_path, monkeypatch
):
    """Stamped before git starts, so a container OOM-killed mid-repack leaves
    it behind; removed once the repack is done."""
    clone_path = _fake_clone(tmp_path)
    out = tmp_path / "seen"
    marker = git_fetcher._repack_failed_marker(clone_path)
    _install_git_shim(
        tmp_path, monkeypatch, f'[ -f "{marker}" ] && echo stamped > "{out}"\n'
    )
    assert _repack_clone(clone_path, timeout=60) is True
    assert out.read_text().strip() == "stamped"
    assert not marker.exists()


def test_marker_dated_in_the_future_does_not_block_repacks(tmp_path):
    clone_path = _fake_clone(tmp_path)
    git_fetcher._record_repack_failure(clone_path)
    marker = git_fetcher._repack_failed_marker(clone_path)
    assert git_fetcher._repack_failed_recently(clone_path)
    future = time.time() + 7200
    os.utime(marker, (future, future))
    assert not git_fetcher._repack_failed_recently(clone_path)


@pytest.mark.asyncio
async def test_delete_floor_keeps_the_clone_while_a_repack_holds_the_lock(
    tmp_path, monkeypatch, records
):
    """The floor's removal waits for the repack lock and, past its bound,
    leaves the dir and says so."""
    import opal_server.scopes.service as service_module

    repo = _ScopeRepo(tmp_path, "s1")
    await repo.sync()
    svc = _service(tmp_path)  # the scope is gone from the store

    async def _never_free(path):
        return False

    monkeypatch.setattr(service_module, "remove_clone_dir_exclusive", _never_free)
    await svc._purge_local_clone_best_effort(repo.source_id, repo.clone_path, "s1")
    assert repo.clone_path.exists()
    assert any(
        "still holds its lock" in r["message"]
        for r in records
        if r["level"].name == "WARNING"
    )


def test_marker_counts_for_the_cooldown_plus_the_repack_timeout(tmp_path):
    """Stamped when the repack started: a container killed at the end of a
    long repack still restarts into a whole cooldown."""
    clone_path = _fake_clone(tmp_path)
    git_fetcher._record_repack_failure(clone_path)
    marker = git_fetcher._repack_failed_marker(clone_path)
    started = time.time() - git_fetcher._REPACK_FAILURE_COOLDOWN_SECONDS - 60
    os.utime(marker, (started, started))
    assert git_fetcher._repack_failed_recently(clone_path)
    long_ago = started - git_fetcher._repack_timeout_seconds() - 3600
    os.utime(marker, (long_ago, long_ago))
    assert not git_fetcher._repack_failed_recently(clone_path)


def test_index_without_its_pack_for_a_day_goes_at_the_first_sighting(tmp_path):
    """A process change can keep a sweep from seeing an orphan twice; one a day
    old is settled by its mtime, which no clock skew stretches that far."""
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack-ancient.idx").write_bytes(b"x")
    day_ago = time.time() - 2 * 86400
    os.utime(pack / "pack-ancient.idx", (day_ago, day_ago))
    git_fetcher._remove_repack_leftovers(pack, "test")
    assert os.listdir(pack) == []


@pytest.mark.asyncio
async def test_marker_of_a_repack_still_running_elsewhere_is_a_counted_skip(
    tmp_path, monkeypatch, emitted
):
    """The marker of a repack another process still runs (an orphaned git of a
    previous leader) is no failure: the due repack is skipped and counted like
    any repack_running skip, and keeps its mark."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()
    git_fetcher._record_repack_failure(scope.clone_path)
    held = _hold_lock(git_fetcher._repack_lock_dir(scope.clone_path))
    try:
        await GitPolicyFetcher.run_due_repacks({scope.source_id})
    finally:
        os.close(held)
    assert spy.calls == []
    assert _skips(emitted) == [{"reason": "repack_running"}]
    assert scope.source_id in git_fetcher._repacks_due


@pytest.mark.asyncio
async def test_clone_in_cooldown_is_named_once_per_cooldown(
    tmp_path, monkeypatch, records
):
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    scope.push()
    await scope.sync()
    due = git_fetcher._repacks_due[scope.source_id]
    git_fetcher._record_repack_failure(scope.clone_path)
    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    git_fetcher._repacks_due[scope.source_id] = due
    await GitPolicyFetcher.run_due_repacks({scope.source_id})
    infos = [
        r
        for r in records
        if r["level"].name == "INFO" and "did not finish" in r["message"]
    ]
    assert len(infos) == 1
    assert spy.calls == []


@pytest.mark.asyncio
async def test_cancelled_delete_floor_still_releases_the_lock_after_its_rmtree(
    tmp_path,
):
    """Cancelled while its rmtree is still queued for an executor thread, the
    DELETE floor must not drop the work item: the lock fd is closed only by
    it. The default executor is one thread, busy, so the item queues."""
    from concurrent.futures import ThreadPoolExecutor

    clones = tmp_path / "git_sources"
    clone = clones / "src"
    (clone / ".git").mkdir(parents=True)
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(1)
    loop.set_default_executor(executor)
    gate = threading.Event()
    blocker = loop.run_in_executor(None, gate.wait, 10)
    try:
        task = asyncio.ensure_future(git_fetcher.remove_clone_dir_exclusive(str(clone)))
        assert await _wait_for_async(lambda: bool(git_fetcher._repack_lock_fds))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        gate.set()
        await blocker
        assert await _wait_for_async(lambda: not git_fetcher._repack_lock_fds)
        assert not clone.exists()
        assert _lock_is_free(clones)
    finally:
        gate.set()
        executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_clone_whose_marker_predates_the_restart_is_named_once(
    tmp_path, monkeypatch, records
):
    """The documented case: a container OOM-killed mid-repack restarts with
    the marker in place and nothing in memory. The clone is still marked
    due, and the due repack names it once per cooldown instead of
    repacking it."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    git_fetcher._record_repack_failure(scope.clone_path)  # before the restart
    await scope.push_and_sync()
    await scope.push_and_sync()
    assert spy.calls == []
    infos = [
        r
        for r in records
        if r["level"].name == "INFO" and "did not finish" in r["message"]
    ]
    assert len(infos) == 1


# --- refs and reflogs ---------------------------------------------------------
#
# libgit2 keeps every ref of a clone in a file of its own and, with reflogs on
# (its default for a clone), a reflog file beside each. A clone of a repository
# with 63,207 branches held 250 MB of ref files and 250 MB of reflogs on 4 KB
# blocks, against 33 MB of objects. The repack packs the refs into packed-refs
# and removes the reflogs, which nothing in OPAL reads, and scope clones are
# made with reflogs off.


def _loose_refs(repo_path: Path) -> list:
    """The refs kept in files of their own, symbolic ones (pack-refs never
    packs those) left out."""
    git_dir = repo_path / ".git"
    return sorted(
        str(p.relative_to(git_dir))
        for p in (git_dir / "refs").rglob("*")
        if p.is_file() and not p.read_text().startswith("ref: ")
    )


def _reflogs(repo_path: Path) -> list:
    logs = repo_path / ".git" / "logs"
    return sorted(str(p.relative_to(logs)) for p in logs.rglob("*") if p.is_file())


def _refs(repo_path: Path) -> dict:
    out = _git(repo_path, "for-each-ref", "--format=%(refname) %(objectname)").stdout
    return dict(line.split(" ") for line in out.splitlines())


def _reflogs_setting(repo_path: Path) -> str:
    return _git(
        repo_path, "config", "--local", "--get", "core.logAllRefUpdates", check=False
    ).stdout.strip()


def _lock_files(repo_path: Path) -> list:
    """The lock files in a clone's git dir and under its refs, where git's ref
    steps take theirs."""
    git_dir = repo_path / ".git"
    locks = [*git_dir.glob("*.lock"), *(git_dir / "refs").rglob("*.lock")]
    return sorted(str(p.relative_to(git_dir)) for p in locks)


def _record(repo_path: Path) -> str:
    """The op record in the clone's lock file: empty once no op is running."""
    return git_cli.clone_lock_path(repo_path).read_text()


def _record_a_dead_op(repo_path: Path) -> None:
    """What an op whose process died leaves in the clone's lock file: its
    record, which the next op finds."""
    fd = git_cli.take_clone_lock(repo_path)
    assert fd is not None
    git_cli.mark_op_started(fd)
    git_cli.drop_clone_lock(fd)


def _asides(repo_path: Path) -> list:
    """The reflog dirs a repack moved aside to remove."""
    return sorted((repo_path / ".git").glob(f"{git_cli.REFLOGS_SET_ASIDE}*"))


def _ref_step_failures(calls) -> list:
    return [
        tags["step"]
        for metric, tags in calls["increment"]
        if metric == "opal_server.scopes.git_ref_step_failures"
    ]


def test_repack_packs_the_refs_and_drops_the_reflogs(tmp_path, emitted):
    """Every ref ends up in packed-refs with the same target, the reflogs are
    gone, the clone has reflogs off for the fetches after it, and no ref step
    is counted as failed.

    Mutation: dropping the pack-refs step leaves the loose refs; dropping the
    reflog removal leaves .git/logs; dropping the config step leaves the
    setting unset.
    """
    clone_path, commits = _clone_with_fetch_packs(tmp_path, fetches=3)
    clone = pygit2.Repository(str(clone_path))
    clone.create_reference("refs/heads/scopes/s1", commits[1])
    clone.free()
    before = _refs(clone_path)
    assert "refs/heads/scopes/s1" in _loose_refs(clone_path)  # the premise
    assert "refs/remotes/origin/master" in _reflogs(clone_path)

    assert _repack_clone(clone_path, timeout=60) is True

    assert _refs(clone_path) == before
    assert _loose_refs(clone_path) == []
    packed = (clone_path / ".git" / "packed-refs").read_text()
    assert all(
        f" {ref}\n" in packed for ref in before if ref != "refs/remotes/origin/HEAD"
    )
    assert not (clone_path / ".git" / "logs").exists()
    assert _reflogs_setting(clone_path) == "false"
    assert _count_pack_files(clone_path) == 1
    _git(clone_path, "fsck", "--no-progress")
    assert _wait_for(lambda: not _asides(clone_path))
    assert _ref_step_failures(emitted) == []


def _reflogs_settings(repo_path: Path) -> list:
    return _git(
        repo_path, "config", "--local", "--get-all", "core.logAllRefUpdates"
    ).stdout.split()


def test_repack_of_a_clone_git_clone_made_replaces_its_two_reflogs_settings(
    tmp_path, emitted, records
):
    """``git clone -c core.logAllRefUpdates=false``, with no -c for it before
    ``clone``, leaves the setting in the clone's config twice: true, from the
    init clone runs first, then false. git config refuses to set a key with
    more than one value (status 5), so the repack replaces both: no ref step
    fails or warns, the reflogs are set aside and removed, the refs packed.

    Mutation: setting the key without --replace-all fails the config step
    (counted, a WARNING) and leaves the reflogs.
    """
    remote_path = tmp_path / "remote.git"
    remote = _init_remote(remote_path)
    tip = _commit(remote, "package policy\n")
    remote.free()
    clone_path = tmp_path / "clone"
    _git(
        tmp_path,
        "clone",
        "--quiet",
        "--no-checkout",
        "--template=",
        "-c",
        "core.logAllRefUpdates=false",
        str(remote_path),
        str(clone_path),
    )
    # A ref of its own written with reflogs on: a loose ref, and its reflog.
    _git(
        clone_path,
        "-c",
        "core.logAllRefUpdates=true",
        "update-ref",
        "refs/heads/scopes/s1",
        str(tip),
    )
    assert _reflogs_settings(clone_path) == ["true", "false"]  # the premise
    assert "refs/heads/scopes/s1" in _loose_refs(clone_path)
    assert "refs/heads/scopes/s1" in _reflogs(clone_path)
    before = _refs(clone_path)

    assert _repack_clone(clone_path, timeout=60) is True

    assert _ref_step_failures(emitted) == []
    assert [r["message"] for r in records if r["level"].name == "WARNING"] == []
    assert _reflogs_settings(clone_path) == ["false"]
    assert not (clone_path / ".git" / "logs").exists()
    assert _wait_for(lambda: not _asides(clone_path))
    assert _refs(clone_path) == before
    assert _loose_refs(clone_path) == []


@pytest.mark.asyncio
async def test_a_scope_clone_writes_no_reflog(tmp_path):
    """A scope clone is made with reflogs off, so neither its clone, nor a
    fetch, nor a scope's own ref (refs/heads/scopes/<scope>) writes one:
    libgit2 1.9.7 honours core.logAllRefUpdates=false.

    Mutation: cloning without the repository callback that turns them off
    writes a reflog for every ref.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.sync()  # the clone

    assert _reflogs_setting(scope.clone_path) == "false"
    assert _reflogs(scope.clone_path) == []
    tip = await scope.push_and_sync()
    assert scope.notified[-1][1] == tip
    assert _refs(scope.clone_path)["refs/heads/scopes/s1"] == tip
    assert _reflogs(scope.clone_path) == []


@pytest.mark.asyncio
async def test_a_clone_whose_config_cannot_be_written_fails_as_a_clone_does(
    tmp_path, monkeypatch, emitted, records
):
    """Turning reflogs off writes the new clone's config, which the clone
    itself writes next (its remote): when that cannot be done (here another
    process holds config.lock), the clone fails like any clone, counted, logged
    and backed off, and leaves no repository behind, so the next sync that gets
    to it clones again, with reflogs off.

    Mutation: leaving the repository in place fails the next sync on a
    remote that does not match.
    """
    real_init = pygit2.init_repository
    made: list = []

    def _init_then_lock_the_config(path, *args, **kwargs):
        repo = real_init(path, *args, **kwargs)
        lock = Path(os.fsdecode(path)) / ".git" / "config.lock"
        lock.write_text("[core]\n")
        made.append(lock)
        return repo

    scope = _ScopeRepo(tmp_path, "s1")
    monkeypatch.setattr(
        git_fetcher.pygit2, "init_repository", _init_then_lock_the_config
    )
    await scope.sync()
    monkeypatch.setattr(git_fetcher.pygit2, "init_repository", real_init)

    assert made, "the repository callback never ran; test proves nothing"
    assert not scope.clone_path.exists()
    assert scope.notified == []
    failures = [
        tags
        for metric, tags in emitted["increment"]
        if metric == "opal_server.scopes.git_op_failures"
    ]
    assert failures == [{"op": "clone", "reason": "git_error"}]
    assert [
        r
        for r in records
        if r["level"].name == "ERROR" and "Could not clone" in r["message"]
    ]

    await scope.sync(honor_backoff=False)
    assert scope.notified[-1][1] == str(scope.tip)
    assert _reflogs_setting(scope.clone_path) == "false"


@pytest.mark.asyncio
async def test_a_housekept_clone_serves_the_same_bundles(tmp_path):
    """Packing the refs changes how they are stored, not what they name: the
    full bundle and a diff bundle are the same before and after, and the next
    sync finds the scope's own ref where it was (no change to tell)."""
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(2)
    first, tip = scope.notified[0][1], str(scope.tip)
    full = scope.fetcher.make_bundle()
    diff = scope.fetcher.make_bundle(first)
    assert (diff.old_hash, diff.hash) == (first, tip)  # the premise: a real diff
    GitPolicyFetcher.forget_repo(str(scope.clone_path))

    assert _repack_clone(scope.clone_path, timeout=60) is True
    assert _loose_refs(scope.clone_path) == []

    assert scope.fetcher.make_bundle() == full
    assert scope.fetcher.make_bundle(first) == diff
    await scope.sync()
    assert scope.notified[-1][:2] == (tip, tip)


@pytest.mark.asyncio
async def test_libgit2_and_git_fetch_a_housekept_clone(tmp_path, monkeypatch):
    """On a clone whose refs are all packed, the scope fetcher's libgit2 fetch
    and its git fetch (SCOPES_GIT_FETCH_WITH_CLI) both move a branch, bring a
    new one and, with prune on, remove one the remote deleted; neither writes a
    reflog.

    Prune goes on once the refs are packed: with the libgit2 fetch
    pruning the ref steps leave them loose (_packing_refs), and a clone git
    made has them packed.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(2)
    scope.remote.create_reference("refs/heads/env2", scope.tip)
    await scope.sync()
    GitPolicyFetcher.forget_repo(str(scope.clone_path))
    assert _repack_clone(scope.clone_path, timeout=60) is True
    assert _loose_refs(scope.clone_path) == []
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)
    clone = scope.clone_path

    # libgit2, through the scope fetcher
    tip = str(scope.push())
    scope.remote.create_reference("refs/heads/env3", scope.tip)
    scope.remote.references.delete("refs/heads/env2")
    await scope.sync()
    refs = _refs(clone)
    assert refs["refs/remotes/origin/master"] == tip
    assert refs["refs/remotes/origin/env3"] == tip
    assert "refs/remotes/origin/env2" not in refs
    assert scope.notified[-1][1] == tip

    # git, through the scope fetcher, of every branch (as a pass whose scopes
    # track more branches than SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES): a
    # refresh of s1 would ask for its own branch alone.
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 0
    )
    tip = str(scope.push())
    scope.remote.create_reference("refs/heads/env4", scope.tip)
    scope.remote.references.delete("refs/heads/env3")
    await scope.sync()
    refs = _refs(clone)
    assert refs["refs/remotes/origin/master"] == tip
    assert refs["refs/remotes/origin/env4"] == tip
    assert "refs/remotes/origin/env3" not in refs
    assert scope.notified[-1][1] == tip

    assert _reflogs(clone) == []
    _git(clone, "fsck", "--no-progress")


@pytest.mark.asyncio
async def test_a_clone_made_with_reflogs_is_cleaned_by_its_next_pass(tmp_path, emitted):
    """A clone made before scope clones had reflogs off, its refs loose and a
    reflog for each, is cleaned by the ref steps alone at the end of the first
    pass after a fetch of it, well below the pack limit, and writes no reflog
    after it."""
    scope = _ScopeRepo(tmp_path, "s1")
    pygit2.clone_repository(scope.fetcher._source.url, str(scope.clone_path)).free()
    await scope.sync()
    assert _reflogs_setting(scope.clone_path) == "true"  # the premise
    assert "refs/heads/scopes/s1" in _reflogs(scope.clone_path)
    assert "refs/heads/scopes/s1" in _loose_refs(scope.clone_path)
    packs = _count_pack_files(scope.clone_path)

    await scope.sync_pass()

    assert _pack_refs_outcomes(emitted) == ["ok"]
    assert _repack_outcomes(emitted) == []
    assert _count_pack_files(scope.clone_path) == packs
    assert _loose_refs(scope.clone_path) == []
    assert not (scope.clone_path / ".git" / "logs").exists()
    assert _reflogs_setting(scope.clone_path) == "false"
    tip = await scope.push_and_sync()
    assert scope.notified[-1][1] == tip
    assert not (scope.clone_path / ".git" / "logs").exists()


@pytest.mark.asyncio
async def test_a_fresh_libgit2_clone_ends_packed_after_one_pass(
    tmp_path, emitted, spans, records
):
    """A libgit2 clone keeps each ref in a file of its own (259 MB on 4 KB
    blocks for a repository with 63,000 branches) until its first repack,
    SCOPES_GIT_REPACK_PACK_LIMIT fetches later. The clone marks it due for the
    ref steps alone, and the next pass runs them: every ref packed, with the
    same target, and no pack merged. Counted, traced and logged apart from
    repacks. Once its refs are packed, its fetches mark it no more.

    Mutation: not marking a clone whose refs are unpacked, or not marking
    after a clone, leaves the refs loose; running the whole repack below the
    limit merges the clone's objects into a pack.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    for i in range(5):
        scope.remote.create_reference(f"refs/heads/env{i}", scope.tip)

    await scope.sync()  # the clone, outside a pass

    clone = scope.clone_path
    assert set(git_fetcher._repacks_due) == {scope.source_id}
    assert "refs/remotes/origin/env4" in _loose_refs(clone)  # the premise
    before = _refs(clone)
    packs = _count_pack_files(clone)

    await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert _loose_refs(clone) == []
    assert _refs(clone) == before
    assert _count_pack_files(clone) == packs
    assert _pack_refs_outcomes(emitted) == ["ok"]
    assert _repack_outcomes(emitted) == []
    assert len(spans.pack_refs_spans()) == 1
    assert spans.repack_spans() == []
    assert [
        r
        for r in records
        if r["level"].name == "INFO" and "Packed the refs" in r["message"]
    ]
    await scope.sync()
    assert git_fetcher._repacks_due == {}
    tip = await scope.push_and_sync()
    assert scope.notified[-1][1] == tip
    assert git_fetcher._repacks_due == {}
    assert _pack_refs_outcomes(emitted) == ["ok"]


@pytest.mark.asyncio
async def test_a_clone_whose_refs_were_packed_since_its_mark_is_left_alone(
    tmp_path, emitted
):
    """The pass can end long after the clone that marked it, and something else
    (a repack in another process, say) may have packed its refs since.

    Mutation: not checking again at the due run runs the ref steps anyway.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.sync()
    assert set(git_fetcher._repacks_due) == {scope.source_id}
    assert git_fetcher._pack_clone_refs(scope.clone_path, timeout=60) is True

    await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert _pack_refs_outcomes(emitted) == []
    assert git_fetcher._repacks_due == {}


@pytest.mark.asyncio
async def test_a_clone_gone_since_its_mark_is_left_alone(tmp_path, emitted):
    """A later sync of the pass can find the clone invalid and delete it, and
    its clone again fail: the mark stays, for a clone that is no longer
    there. The due run does nothing for it, and counts nothing.

    Mutation: without the check that the clone is there, the ref steps run
    on the missing path, fail, and cool the source down for an hour.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.sync()
    assert set(git_fetcher._repacks_due) == {scope.source_id}
    GitPolicyFetcher.forget_repo(str(scope.clone_path))
    shutil.rmtree(scope.clone_path)

    await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert _pack_refs_outcomes(emitted) == []
    assert _repack_outcomes(emitted) == []
    assert git_fetcher._repack_failed_at == {}
    assert git_fetcher._repacks_due == {}


def test_a_clone_that_cannot_be_read_has_no_ref_steps_due(tmp_path):
    """The check never raises: the mark after a fetch never fails the sync,
    and the due run never ends the pass's other repacks. A clone dir with mode
    000, whose .git a stat then fails with EACCES.
    """
    clone = _fake_clone(tmp_path)
    clone.chmod(0)
    try:
        if os.access(clone, os.X_OK):
            pytest.skip("this user reads every directory (root)")
        assert git_fetcher._ref_steps_due(clone) is False
    finally:
        clone.chmod(stat.S_IRWXU)


@pytest.mark.asyncio
async def test_a_git_clone_is_not_marked_for_its_refs(tmp_path, monkeypatch):
    """Git clone writes the refs into packed-refs itself, so a clone made with
    SCOPES_GIT_FETCH_WITH_CLI on is marked only at the pack limit."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    scope = _ScopeRepo(tmp_path, "s1")

    await scope.sync()

    assert (scope.clone_path / ".git" / "packed-refs").exists()
    assert git_fetcher._repacks_due == {}
    tip = await scope.push_and_sync()
    assert scope.notified[-1][1] == tip
    assert git_fetcher._repacks_due == {}


@pytest.mark.asyncio
async def test_a_libgit2_fetch_that_prunes_keeps_the_refs_in_files_of_their_own(
    tmp_path, monkeypatch, emitted
):
    """libgit2 removes a pruned ref's own file, but rewrites the whole
    packed-refs file for each ref it prunes from it: pruning 3,000 refs from
    a clone of a repository with 25,000 branches took 16 s packed, 0.5 s
    loose. With the libgit2 fetch pruning (SCOPES_GIT_FETCH_WITH_CLI off,
    SCOPES_GIT_FETCH_PRUNE on) the ref steps therefore leave the refs loose:
    a fresh clone, made with no reflogs, is not marked for them, and the
    repack at the pack limit merges the packs without packing a ref. The
    pruning fetch after it removes the deleted branch.

    Mutation: packing the refs anyway, in the repack or in a run of the ref
    steps alone, fails it.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)
    scope = _ScopeRepo(tmp_path, "s1")
    scope.remote.create_reference("refs/heads/env2", scope.tip)
    clone = scope.clone_path

    await scope.fetched(_LIMIT - 1)
    assert git_fetcher._repacks_due == {}
    await scope.push_and_sync()  # the fetch that reaches the limit

    assert _repack_outcomes(emitted) == ["ok"]
    assert _count_pack_files(clone) == 1
    assert _pack_refs_outcomes(emitted) == []
    assert not (clone / ".git" / "packed-refs").exists()
    assert "refs/remotes/origin/env2" in _loose_refs(clone)
    scope.remote.references.delete("refs/heads/env2")
    tip = await scope.push_and_sync()
    refs = _refs(clone)
    assert "refs/remotes/origin/env2" not in refs
    assert refs["refs/remotes/origin/master"] == tip
    assert scope.notified[-1][1] == tip
    assert _reflogs(clone) == []


@pytest.mark.asyncio
async def test_with_libgit2_pruning_the_ref_steps_alone_remove_the_reflogs(
    tmp_path, monkeypatch, emitted, records
):
    """A clone made with reflogs on (by an earlier version) still gets the ref
    steps alone at the end of the next pass with the libgit2 fetch pruning:
    they turn its reflogs off and remove them, leave its refs in files of
    their own, and are logged as such. Its fetches mark it no more after it.

    Mutation: marking a clone for its loose refs whatever the settings runs
    the ref steps after every fetch.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)
    scope = _ScopeRepo(tmp_path, "s1")
    clone = scope.clone_path
    pygit2.clone_repository(scope.fetcher._source.url, str(clone)).free()
    await scope.sync()
    assert "refs/heads/scopes/s1" in _reflogs(clone)  # the premise
    assert set(git_fetcher._repacks_due) == {scope.source_id}

    await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert _pack_refs_outcomes(emitted) == ["ok"]
    assert _reflogs_setting(clone) == "false"
    assert not (clone / ".git" / "logs").exists()
    assert _wait_for(lambda: not _asides(clone))
    assert "refs/heads/scopes/s1" in _loose_refs(clone)
    assert not (clone / ".git" / "packed-refs").exists()
    assert [
        r
        for r in records
        if r["level"].name == "INFO" and "Removed the reflogs of" in r["message"]
    ]
    tip = await scope.push_and_sync()
    assert scope.notified[-1][1] == tip
    assert git_fetcher._repacks_due == {}
    assert _pack_refs_outcomes(emitted) == ["ok"]
    assert not (clone / ".git" / "logs").exists()


@pytest.mark.asyncio
async def test_with_libgit2_pruning_a_failed_config_alone_waits_out_the_cooldown(
    tmp_path, monkeypatch, emitted, records
):
    """With the refs left loose, git config is the one git of a run of the
    ref steps alone: when it fails, the run fails, logged with git's stderr
    and cooled down as a failed pack-refs is, rather than run again at the
    end of every pass.

    Mutation: only warning, as when a repack follows, runs it on every pass.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)
    real_git = shutil.which("git")
    state = tmp_path / "state"
    state.mkdir()
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'if [ "$3" = config ]; then\n'
        f'  echo x >> "{state}/config"\n'
        "  echo 'error: could not lock config file' >&2\n"
        "  exit 255\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        refs_steps=True,
    )
    scope = _ScopeRepo(tmp_path, "s1")
    pygit2.clone_repository(scope.fetcher._source.url, str(scope.clone_path)).free()
    await scope.sync()

    await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert _pack_refs_outcomes(emitted) == ["error"]
    assert scope.source_id in git_fetcher._repack_failed_at
    [warning] = [
        r
        for r in records
        if r["level"].name == "WARNING" and "Removing the reflogs" in r["message"]
    ]
    assert "git config exited with status 255" in warning["message"]
    assert "could not lock config file" in warning["message"]
    await scope.sync_pass()
    await scope.push_and_sync()
    assert (state / "config").read_text().split() == ["x"]
    assert _pack_refs_outcomes(emitted) == ["error"]
    assert _ref_step_failures(emitted) == ["config"]
    assert (scope.clone_path / ".git" / "logs").exists()


@pytest.mark.asyncio
async def test_the_ref_steps_alone_wait_while_a_git_op_holds_the_clone(
    tmp_path, emitted
):
    """A clone due for its ref steps alone whose lock a git command-line op
    holds (one of another process, say) is skipped as a repack is: counted as
    git_op_skipped with reason clone_busy, its mark kept, and packed by the
    next pass once the lock is free.

    Mutation: letting the busy clone fail the run, or dropping the mark,
    fails it.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.sync()  # the clone: marked for its ref steps
    assert set(git_fetcher._repacks_due) == {scope.source_id}
    holder = git_cli.take_clone_lock(scope.clone_path)
    assert holder is not None
    try:
        await GitPolicyFetcher.run_due_repacks({scope.source_id})
    finally:
        git_cli.drop_clone_lock(holder)

    assert {"reason": "clone_busy"} in _skips(emitted)
    assert set(git_fetcher._repacks_due) == {scope.source_id}
    assert _pack_refs_outcomes(emitted) == []
    assert git_fetcher._repack_failed_at == {}
    assert "refs/remotes/origin/master" in _loose_refs(scope.clone_path)

    await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert _pack_refs_outcomes(emitted) == ["ok"]
    assert _loose_refs(scope.clone_path) == []


@pytest.mark.asyncio
async def test_a_failed_pack_refs_alone_waits_out_the_cooldown(
    tmp_path, monkeypatch, emitted, records
):
    """With nothing else to run, a pack-refs that fails fails the run, which is
    counted, logged with git's stderr and cooled down as a failed repack is,
    rather than run again at the end of every pass.

    Mutation: only warning, as when a repack follows, runs it on every pass.
    """
    real_git = shutil.which("git")
    state = tmp_path / "state"
    state.mkdir()
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'if [ "$3" = pack-refs ]; then\n'
        f'  echo x >> "{state}/pack-refs"\n'
        "  echo 'fatal: out of memory' >&2\n"
        "  exit 128\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        refs_steps=True,
    )
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.sync()

    await GitPolicyFetcher.run_due_repacks({scope.source_id})

    assert _pack_refs_outcomes(emitted) == ["error"]
    assert scope.source_id in git_fetcher._repack_failed_at
    [warning] = [
        r
        for r in records
        if r["level"].name == "WARNING" and "Packing the refs" in r["message"]
    ]
    assert "git pack-refs exited with status 128" in warning["message"]
    assert "out of memory" in warning["message"]
    await scope.sync_pass()
    await scope.push_and_sync()
    assert (state / "pack-refs").read_text().split() == ["x"]
    assert _pack_refs_outcomes(emitted) == ["error"]
    assert _ref_step_failures(emitted) == ["pack_refs"]


def test_packed_refs_keep_annotated_tags_peeled_and_head_symbolic(tmp_path):
    """git pack-refs writes an annotated tag followed by a "^" line with the
    commit it peels to, and leaves a symbolic ref (refs/remotes/origin/HEAD)
    in a file of its own: a fresh libgit2 handle reads each as before, and a
    libgit2 fetch after it moves the branch that HEAD names."""
    clone_path, commits = _clone_with_fetch_packs(tmp_path, fetches=1)
    clone = pygit2.Repository(str(clone_path))
    tag = clone.create_tag(
        "v1", commits[0], pygit2.enums.ObjectType.COMMIT, _SIG, "release"
    )
    clone.create_reference("refs/tags/light", commits[1])
    clone.free()
    before = _refs(clone_path)

    assert git_fetcher._pack_clone_refs(clone_path, timeout=60) is True

    assert _loose_refs(clone_path) == []
    assert _refs(clone_path) == before
    packed = (clone_path / ".git" / "packed-refs").read_text().splitlines()
    line = packed.index(f"{tag} refs/tags/v1")
    assert packed[line + 1] == f"^{commits[0]}"
    remote = pygit2.Repository(str(tmp_path / "remote.git"))
    tip = _commit(remote, "package policy\n# after packing\n", remote.head.target)
    remote.free()
    fresh = pygit2.Repository(str(clone_path))
    try:
        ref = fresh.lookup_reference("refs/tags/v1")
        assert ref.target == tag
        assert ref.peel(pygit2.Commit).id == commits[0]
        assert fresh.revparse_single("v1^{commit}").id == commits[0]
        assert fresh.lookup_reference("refs/tags/light").target == commits[1]
        head = fresh.lookup_reference("refs/remotes/origin/HEAD")
        assert head.type == pygit2.enums.ReferenceType.SYMBOLIC
        assert head.target == "refs/remotes/origin/master"
        assert head.resolve().target == commits[1]
        fresh.remotes["origin"].fetch()
        assert (
            fresh.lookup_reference("refs/remotes/origin/HEAD").resolve().target == tip
        )
    finally:
        fresh.free()
    _git(clone_path, "fsck", "--no-progress")


def test_readers_find_every_ref_while_pack_refs_runs(tmp_path):
    """git pack-refs writes packed-refs before it removes any ref's own file,
    and libgit2 looks for a ref's file before packed-refs, which it reloads
    once it changes: a handle opened at any moment of the pack finds every
    ref, with its target."""
    clone_path, commits = _clone_with_fetch_packs(tmp_path, fetches=1)
    clone = pygit2.Repository(str(clone_path))
    expected = {f"refs/remotes/origin/b{i:04d}": commits[i % 2] for i in range(3000)}
    for name, target in expected.items():
        clone.create_reference(name, target)
    clone.free()
    sample = sorted(expected)[::61]
    done = threading.Event()
    lookups: list = []
    wrong: list = []

    def _read() -> None:
        while not done.is_set():
            fresh = pygit2.Repository(str(clone_path))
            try:
                for name in sample:
                    try:
                        target = fresh.lookup_reference(name).target
                    except KeyError:
                        target = None
                    if target != expected[name]:
                        wrong.append((name, target))
                    lookups.append(name)
            finally:
                fresh.free()
            # Readers that never sleep starve every other thread of the GIL:
            # the repack's own Python steps then take minutes.
            time.sleep(0.001)

    readers = [threading.Thread(target=_read) for _ in range(4)]
    for reader in readers:
        reader.start()
    try:
        assert _wait_for(lambda: bool(lookups))
        assert git_fetcher._pack_clone_refs(clone_path, timeout=60) is True
    finally:
        done.set()
        for reader in readers:
            reader.join(10)

    assert _loose_refs(clone_path) == []
    assert wrong == []


def test_reflogs_are_removed_once_the_clone_lock_is_released(tmp_path, monkeypatch):
    """Tens of thousands of reflog files can take longer to remove than the
    repack's timeout on a slow volume, so they are moved aside in one rename
    inside it, and removed on a thread of their own once the repack has
    released the clone's lock: neither the clone's next op nor the repack's
    caller waits for them.

    Mutation: removing them in place leaves nothing set aside; removing them
    before the repack returns holds it up until the removal ends; not
    removing them leaves them set aside.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    gate = threading.Event()
    lock_was_free: list = []
    real_remove = git_cli.remove_tree

    def _slow_remove(path: Path) -> bool:
        fd = git_cli.take_clone_lock(clone_path)
        lock_was_free.append(fd is not None)
        if fd is not None:
            git_cli.drop_clone_lock(fd)
        gate.wait(10)
        return real_remove(path)

    monkeypatch.setattr(git_cli, "remove_tree", _slow_remove)
    try:
        assert _repack_clone(clone_path, timeout=60) is True

        assert not (clone_path / ".git" / "logs").exists()
        assert len(_asides(clone_path)) == 1
        assert _wait_for(lambda: bool(lock_was_free))
        assert lock_was_free == [True]
    finally:
        gate.set()
    assert _wait_for(lambda: not _asides(clone_path))


def test_reflogs_left_set_aside_are_removed_by_the_next_repack_not_the_preload(
    tmp_path,
):
    """A process that died between the rename and the end of the removal leaves
    the reflogs set aside, with no record of an op. The pre-fork preload's
    sweep leaves them: it runs in the gunicorn master before any worker
    exists, and tens of thousands of files per clone would hold up the start.
    The next repack of the clone removes them with its own, once it has let
    go of the clone.

    Mutation: removing them in the preload's sweep, or removing only the dir
    this repack set aside, fails it.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    clones = GitPolicyFetcher.base_dir(tmp_path / "base")
    clones.mkdir(parents=True)
    clone_path = Path(shutil.move(clone_path, clones / "src"))
    git_dir = clone_path / ".git"
    left = git_dir / f"{git_cli.REFLOGS_SET_ASIDE}dead"
    shutil.copytree(git_dir / "logs", left)

    git_fetcher.sweep_scope_clone_leftovers(tmp_path / "base")

    assert left.exists()
    assert _repack_clone(clone_path, timeout=60) is True
    assert _wait_for(lambda: not left.exists())


def _clone_dir_with_reflogs_set_aside(clones: Path, name: str) -> Path:
    git_dir = clones / name / ".git"
    aside = git_dir / f"{git_cli.REFLOGS_SET_ASIDE}dead"
    (aside / "refs" / "remotes" / "origin").mkdir(parents=True)
    (aside / "refs" / "remotes" / "origin" / "main").write_text("0" * 40 + "\n")
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    return aside


def test_reflogs_left_set_aside_in_a_quiet_clone_go_when_a_leader_starts(tmp_path):
    """A quiet clone, whose packs stay under the repack's limit, has no next
    repack to remove the reflogs a dead process set aside: the scopes leader's
    start removes them in every clone, each on a thread of its own, and says
    how many clones had some. Names that are not a clone's, and a symlink to
    one, are not looked into.

    Mutation: leaving this to the next repack keeps them.
    """
    clones = GitPolicyFetcher.base_dir(tmp_path / "base")
    asides = [_clone_dir_with_reflogs_set_aside(clones, f"{c * 64}-0") for c in "ab"]
    _clone_dir_with_reflogs_set_aside(clones, f"{'c' * 64}-1").parent.joinpath(
        f"{git_cli.REFLOGS_SET_ASIDE}0"
    ).mkdir()
    kept = [
        _clone_dir_with_reflogs_set_aside(clones, "not-a-source-id"),
        _clone_dir_with_reflogs_set_aside(tmp_path / "elsewhere", f"{'d' * 64}-0"),
    ]
    (clones / f"{'d' * 64}-0").symlink_to(kept[1].parent.parent)
    quiet = clones / f"{'e' * 64}-0"
    (quiet / ".git").mkdir(parents=True)

    assert git_fetcher.remove_reflogs_left_set_aside(tmp_path / "base") == 3

    assert _wait_for(lambda: not any(a.exists() for a in asides))
    assert _wait_for(lambda: not _asides(clones / f"{'c' * 64}-1"))
    assert all(k.exists() for k in kept)


def test_no_clones_dir_means_no_reflogs_to_remove(tmp_path):
    assert git_fetcher.remove_reflogs_left_set_aside(tmp_path / "base") == 0


def test_a_clones_dir_that_cannot_be_listed_is_logged_not_raised(
    tmp_path, monkeypatch, records
):
    clones = GitPolicyFetcher.base_dir(tmp_path / "base")
    _clone_dir_with_reflogs_set_aside(clones, f"{'a' * 64}-0")
    scandir = os.scandir

    def _scandir(path="."):
        if Path(path) == clones:
            raise PermissionError(13, "Permission denied")
        return scandir(path)

    monkeypatch.setattr(git_fetcher.os, "scandir", _scandir)

    assert git_fetcher.remove_reflogs_left_set_aside(tmp_path / "base") == 0
    assert [
        (r["level"].name, r["message"]) for r in records if "set aside" in r["message"]
    ] == [
        (
            "WARNING",
            f"Could not look for reflogs set aside in {clones}: "
            "PermissionError(13, 'Permission denied')",
        )
    ]


def _reflog_thread_ahead_of_unlink(monkeypatch) -> None:
    """os.unlink with the reflog removal thread running ahead of it in the same
    directory: by the first reflog file a delete removes, the thread has
    removed the others, which the delete has already listed."""
    real_unlink = os.unlink
    ahead: list = []

    def _unlink(path, *, dir_fd=None):
        name = os.path.basename(path)
        if name.startswith("reflog-") and not ahead:
            ahead.append(name)
            where = dir_fd if dir_fd is not None else os.path.dirname(path)
            for other in os.listdir(where):
                if other.startswith("reflog-") and other != name:
                    if dir_fd is None:
                        other = os.path.join(where, other)
                    real_unlink(other, dir_fd=dir_fd)
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", _unlink)


@pytest.mark.parametrize("by", ["recovery", "delete"])
@pytest.mark.asyncio
async def test_a_clone_delete_beside_the_reflog_removal_thread_removes_it_all(
    tmp_path, monkeypatch, by
):
    """The reflog removal thread runs outside the clone's lock, so a delete of
    the clone (invalid-repo recovery, a DELETE) can walk the reflogs the thread
    is removing, and find gone an entry it listed.

    Stopped there with a FileNotFoundError, the delete would leave the
    rest, and the callers would take that error for the clone being gone
    already.
    """
    clone = tmp_path / "git_sources" / "src"
    aside = clone / ".git" / f"{git_cli.REFLOGS_SET_ASIDE}0001"
    aside.mkdir(parents=True)
    for i in range(3):
        (aside / f"reflog-{i}").write_text("0" * 40 + "\n")
    (clone / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    _reflog_thread_ahead_of_unlink(monkeypatch)

    if by == "recovery":
        removed = await run_sync(git_fetcher._rmtree_unless_locked, str(clone))
    else:
        removed = await git_fetcher.remove_clone_dir_exclusive(str(clone))

    assert removed is True
    assert not clone.exists()


def test_a_config_step_that_finds_a_live_lock_leaves_it_and_still_packs_the_refs(
    tmp_path, records, emitted
):
    """Git config fails on a config.lock another process holds (no op recorded
    for the clone, so a live one): that lock stays, since git only leaves its
    own when killed; the reflogs stay, since git would go on appending to them
    with reflogs still on; the refs are packed all the same, the repack runs,
    the failure is counted, and the record cleared.

    Mutation: removing the reflogs anyway, skipping pack-refs, removing the
    lock after an exit with a status, or failing the repack each fail it.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    config_lock = clone_path / ".git" / "config.lock"
    config_lock.write_text("[core]\n")
    assert "refs/remotes/origin/master" in _reflogs(clone_path)  # the premise

    assert _repack_clone(clone_path, timeout=60) is True

    assert _count_pack_files(clone_path) == 1
    assert _loose_refs(clone_path) == []
    assert "refs/remotes/origin/master" in _reflogs(clone_path)
    assert _lock_files(clone_path) == ["config.lock"]
    [warning] = [
        r
        for r in records
        if r["level"].name == "WARNING" and "git config" in r["message"]
    ]
    assert "lock" in warning["message"]
    assert _ref_step_failures(emitted) == ["config"]
    assert _record(clone_path) == ""


def test_a_live_holders_ref_locks_survive_the_repack(tmp_path, records, emitted):
    """With no op recorded for the clone, a packed-refs.lock or ref lock in it
    may be a live op's (a libgit2 one takes no clone lock): the repack leaves
    them at its start, its pack-refs then exits 128 on packed-refs.lock, and
    after an exit with a status they are still not the repack's to remove. The
    refs stay loose, it is counted, and git repack runs.

    Mutation: removing what is left at the start whatever the record says, or
    after any failed step, removes the live holder's locks.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    git_dir = clone_path / ".git"
    held = [
        git_dir / "packed-refs.lock",
        git_dir / "refs" / "remotes" / "origin" / "x.lock",
    ]
    for lock in held:
        lock.write_text("held\n")

    assert _repack_clone(clone_path, timeout=60) is True

    assert [lock for lock in held if not lock.exists()] == []
    assert "refs/remotes/origin/master" in _loose_refs(clone_path)
    assert _count_pack_files(clone_path) == 1
    assert _ref_step_failures(emitted) == ["pack_refs"]
    [warning] = [
        r
        for r in records
        if r["level"].name == "WARNING" and "pack-refs" in r["message"]
    ]
    assert "status 128" in warning["message"]
    assert "packed-refs.lock" in warning["message"]


def test_locks_a_dead_op_left_are_removed_whatever_their_age(tmp_path):
    """When the clone's lock file records an op that never finished, its
    process died with its git running: the locks in the clone are that git's,
    however fresh, and go before the ref steps run, which then pack every ref.

    Mutation: not removing them first leaves packed-refs.lock in place and
    the refs loose (pack-refs fails on it).
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    git_dir = clone_path / ".git"
    locks = [
        git_dir / "packed-refs.lock",
        git_dir / "config.lock",
        git_dir / "refs" / "remotes" / "origin" / "master.lock",
    ]
    for lock in locks:
        lock.touch()
    _record_a_dead_op(clone_path)

    assert _repack_clone(clone_path, timeout=60) is True

    assert [lock for lock in locks if lock.exists()] == []
    assert _loose_refs(clone_path) == []
    assert _reflogs_setting(clone_path) == "false"
    assert _count_pack_files(clone_path) == 1
    assert _record(clone_path) == ""


def test_a_repack_stays_recorded_while_what_a_dead_op_left_cannot_be_removed(
    tmp_path,
):
    """Something a dead op left that cannot be removed (a directory where
    packed-refs.new would be) keeps the repack recorded in the clone's lock
    file, for the next op on the clone to try again; the repack itself is done,
    and once that is gone the next repack clears the record.

    Mutation: clearing the record whatever the clean-up managed fails it.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    git_dir = clone_path / ".git"
    stuck = git_dir / "packed-refs.new"
    (stuck / "x").mkdir(parents=True)
    _record_a_dead_op(clone_path)

    assert _repack_clone(clone_path, timeout=60) is True

    assert _count_pack_files(clone_path) == 1
    assert _record(clone_path).strip() == str(os.getpid())
    shutil.rmtree(stuck)
    assert _repack_clone(clone_path, timeout=60) is True
    assert _record(clone_path) == ""
    assert _loose_refs(clone_path) == []


def test_reflogs_that_cannot_be_removed_are_counted_and_the_repack_still_runs(
    tmp_path, records, emitted
):
    """Reflogs whose removal fails (a directory in them the server cannot write
    to) stay set aside: a warning, counted, and the repack is done all the
    same. Once they can go, the next repack removes them with its own.

    Mutation: not counting the failure, or failing the repack on it, fails it.
    """
    if os.geteuid() == 0:
        pytest.skip("root removes them anyway")
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    git_dir = clone_path / ".git"
    origin_logs = Path("refs") / "remotes" / "origin"
    (git_dir / "logs" / origin_logs).chmod(0o500)
    try:
        assert _repack_clone(clone_path, timeout=60) is True

        assert _count_pack_files(clone_path) == 1
        assert _loose_refs(clone_path) == []
        assert _reflogs_setting(clone_path) == "false"
        assert _wait_for(lambda: _ref_step_failures(emitted) == ["reflogs"])
        [aside] = _asides(clone_path)
        assert [
            r
            for r in records
            if r["level"].name == "WARNING" and str(aside) in r["message"]
        ]
    finally:
        for stuck in [a / origin_logs for a in _asides(clone_path)]:
            stuck.chmod(0o700)

    assert _repack_clone(clone_path, timeout=60) is True
    assert _wait_for(lambda: not _asides(clone_path))
    assert _ref_step_failures(emitted) == ["reflogs"]


def test_reflogs_that_cannot_be_moved_aside_stay_and_are_counted(
    tmp_path, monkeypatch, records, emitted
):
    """A rename of logs/ that fails leaves the reflogs where they are, which is
    a warning, counted, and the refs are still packed and the repack done.

    Mutation: not counting it, or failing the repack on it, fails it.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    real_rename = os.rename

    def _rename(src, dst, **kwargs):
        if Path(src).name == "logs":
            raise PermissionError(errno.EACCES, "Permission denied", str(src))
        return real_rename(src, dst, **kwargs)

    monkeypatch.setattr(os, "rename", _rename)

    assert _repack_clone(clone_path, timeout=60) is True

    assert "refs/remotes/origin/master" in _reflogs(clone_path)
    assert _loose_refs(clone_path) == []
    assert _count_pack_files(clone_path) == 1
    assert _ref_step_failures(emitted) == ["reflogs"]
    assert [
        r
        for r in records
        if r["level"].name == "WARNING" and "Could not move" in r["message"]
    ]


@pytest.mark.parametrize("refs_only", [False, True], ids=["repack", "refs-only"])
def test_a_config_step_stopped_at_its_share_of_the_timeout_leaves_no_config_lock(
    tmp_path, monkeypatch, emitted, refs_only
):
    """Git config holding config.lock past the ref steps' share of the timeout
    is stopped like pack-refs, and its lock removed once its group is gone, the
    record cleared. Before a repack, pack-refs is skipped and git repack runs;
    with the ref steps alone, TimeoutError names the step. Counted as a failed
    ref step either way.

    Mutation: not cleaning up after the stop leaves config.lock; not waiting
    for the watchdog after the SIGKILL leaves the locks held under CPU load;
    raising before counting misses the ref steps alone.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    real_git = shutil.which("git")
    real_path = os.environ["PATH"]
    state = tmp_path / "state"
    state.mkdir()
    _install_git_shim(
        tmp_path,
        monkeypatch,
        f'echo "$3" >> "{state}/ran"\n'
        'if [ "$3" = config ]; then\n'
        '  : > "$2/.git/config.lock"\n'
        "  trap '' TERM\n"
        f'  : > "{state}/ready"\n'
        "  while :; do /bin/sleep 1; done\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        refs_steps=True,
    )

    # Timeouts long enough for the shim to start on a loaded machine: the
    # deadline runs from before git config is spawned.
    if refs_only:
        with pytest.raises(TimeoutError, match="timeout ran out during git config"):
            git_fetcher._pack_clone_refs(clone_path, timeout=6, term_grace=0.5)
    else:
        assert _repack_clone(clone_path, timeout=8, term_grace=0.5) is True
        assert _count_pack_files(clone_path) == 1
    assert _ref_step_failures(emitted) == ["config"]

    assert (state / "ready").exists(), "git config never ran; test proves nothing"
    assert "pack-refs" not in (state / "ran").read_text().split()
    assert _lock_files(clone_path) == []
    assert _record(clone_path) == ""
    # Nothing of the SIGKILLed group, its watchdog included (which sh does
    # not reap then), still holds the repack's or the clone's lock.
    assert _free_once_a_stop_returns(
        lambda: _lock_is_free(git_fetcher._repack_lock_dir(clone_path))
    )
    assert _free_once_a_stop_returns(lambda: _clone_lock_is_free(clone_path))
    monkeypatch.setenv("PATH", real_path)
    assert _repack_clone(clone_path, timeout=60) is True
    assert _loose_refs(clone_path) == []


def test_an_interrupted_ref_step_stops_its_git_and_removes_its_locks(
    tmp_path, monkeypatch
):
    """Anything but the deadline unwinding through a ref step (a
    KeyboardInterrupt in a foreground run) stops its git's group with no grace,
    removes what it left once it is gone, clears the record, and is re-raised.

    Mutation: re-raising without stopping git leaves it running.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    state = tmp_path / "state"
    state.mkdir()
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'if [ "$3" = pack-refs ]; then\n'
        '  : > "$2/.git/packed-refs.lock"\n'
        f'  echo $$ > "{state}/git.pid"\n'
        "  exec /bin/sleep 30\n"
        "fi\n"
        f'exec "{shutil.which("git")}" "$@"\n',
        refs_steps=True,
    )
    real_communicate = subprocess.Popen.communicate
    interrupted: list = []

    def _communicate(self, *args, **kwargs):
        if "pack-refs" in self.args and not interrupted:
            interrupted.append(True)
            assert _wait_for(lambda: (state / "git.pid").exists())
            raise KeyboardInterrupt
        return real_communicate(self, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "communicate", _communicate)

    with pytest.raises(KeyboardInterrupt):
        _repack_clone(clone_path, timeout=60)

    assert _wait_gone(int((state / "git.pid").read_text()))
    assert _lock_files(clone_path) == []
    assert _record(clone_path) == ""


_KILL_TEST_BRANCHES = 1000


def _timed_repack(clone_path: Path, monkeypatch) -> dict:
    """Repack ``clone_path``, timing each git command of it.

    Returns {its subcommand: (start, end)}, in seconds from the repack's
    start.
    """
    real_run = git_fetcher._RepackStep.run
    started = time.monotonic()
    times: dict = {}

    def _run(self, argv, **kwargs):
        begin = time.monotonic() - started
        try:
            return real_run(self, argv, **kwargs)
        finally:
            command = next(a for a in argv if a in ("config", "pack-refs", "repack"))
            times[command] = (begin, time.monotonic() - started)

    monkeypatch.setattr(git_fetcher._RepackStep, "run", _run)
    try:
        assert _repack_clone(clone_path, timeout=60) is True
    finally:
        monkeypatch.setattr(git_fetcher._RepackStep, "run", real_run)
    return times


def test_a_repack_killed_anywhere_in_pack_refs_loses_no_ref(
    tmp_path, monkeypatch, emitted
):
    """Its pack-refs SIGKILLed (no grace) at points spread over its run, by the
    ref steps' share of the timeout running out, a repack leaves every ref with
    the target it had, for git and for libgit2, no lock and no record behind,
    and a clone that fsck accepts and the next repack packs."""
    clone_path, commits = _clone_with_fetch_packs(tmp_path, fetches=2)
    clone = pygit2.Repository(str(clone_path))
    for i in range(_KILL_TEST_BRANCHES):
        clone.create_reference(f"refs/remotes/origin/b{i:05d}", commits[i % 3])
    clone.free()
    template = tmp_path / "template"
    shutil.copytree(clone_path, template / "clone", symlinks=True)
    before = _refs(template / "clone")
    assert len(before) > _KILL_TEST_BRANCHES  # the premise
    calibration = tmp_path / "calibration"
    shutil.copytree(template, calibration, symlinks=True)
    times = _timed_repack(calibration / "clone", monkeypatch)
    start, end = times["pack-refs"]
    assert end - start > 0.01, f"pack-refs too quick to stop part-way: {times}"
    share = git_fetcher._REF_STEPS_TIMEOUT_SHARE

    states = []
    for i, fraction in enumerate((0.05, 0.25, 0.5, 0.75, 0.95, 1.2)):
        work = tmp_path / f"kill-{i}"
        shutil.copytree(template, work, symlinks=True)
        clone_path = work / "clone"
        refs_deadline = start + (end - start) * fraction
        stopped_before = len(_ref_step_failures(emitted))
        # The ref steps' share runs out at refs_deadline; git repack gets an
        # hour.
        timeout = max(refs_deadline / share, refs_deadline + 3600)
        monkeypatch.setattr(
            git_fetcher, "_REF_STEPS_TIMEOUT_SHARE", refs_deadline / timeout
        )
        done = _repack_clone(clone_path, timeout=timeout, term_grace=0)
        monkeypatch.setattr(git_fetcher, "_REF_STEPS_TIMEOUT_SHARE", share)
        stopped = len(_ref_step_failures(emitted)) > stopped_before
        state = (fraction, done, stopped, len(_loose_refs(clone_path)))
        states.append(state)

        assert done is True, state
        assert _refs(clone_path) == before, state
        repo = pygit2.Repository(str(clone_path))
        try:
            for name, target in before.items():
                if not name.endswith("/HEAD"):
                    assert str(repo.references[name].target) == target, (name, state)
        finally:
            repo.free()
        assert _lock_files(clone_path) == [], state
        assert _record(clone_path) == "", state
        _git(clone_path, "fsck", "--no-progress")
        assert _repack_clone(clone_path, timeout=60) is True
        assert _loose_refs(clone_path) == []
        assert _refs(clone_path) == before
    assert any(stopped for _, _, stopped, _ in states), states


@pytest.mark.parametrize("refs_only", [False, True], ids=["repack", "refs-only"])
def test_pack_refs_stopped_at_its_share_of_the_timeout_leaves_a_usable_clone(
    tmp_path, monkeypatch, emitted, records, refs_only
):
    """Git pack-refs holds packed-refs.lock while it writes, and a ref's lock
    while it removes that ref's file. Stopped with SIGKILL it leaves them, and
    every later pack-refs, and every fetch that updates or prunes such a ref,
    fails on them. They are removed once its process group is gone, as after a
    stopped fetch. Before a repack the stop is a warning, counted, and git
    repack then runs with the rest of the timeout; with the ref steps alone
    TimeoutError names pack-refs, and the stop is counted too.

    Mutation: not removing the locks after the stop fails the lock asserts
    and the fetch after; cancelling git repack fails "repack"; raising
    before counting fails "refs-only".
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    real_git = shutil.which("git")
    real_path = os.environ["PATH"]
    state = tmp_path / "state"
    state.mkdir()
    ref_lock = clone_path / ".git" / "refs" / "remotes" / "origin" / "master.lock"
    _install_git_shim(
        tmp_path,
        monkeypatch,
        f'echo "$3" >> "{state}/ran"\n'
        'if [ "$3" = pack-refs ]; then\n'
        '  : > "$2/.git/packed-refs.lock"\n'
        f'  : > "{ref_lock}"\n'
        "  trap '' TERM\n"
        f'  : > "{state}/ready"\n'
        "  while :; do /bin/sleep 1; done\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        refs_steps=True,
    )

    # Timeouts long enough for git config and then the shim to start on a
    # loaded machine: the deadline runs from before git config is spawned.
    if refs_only:
        with pytest.raises(TimeoutError, match="timeout ran out during git pack-refs"):
            git_fetcher._pack_clone_refs(clone_path, timeout=6, term_grace=0.5)
        assert _ref_step_failures(emitted) == ["pack_refs"]
    else:
        assert _repack_clone(clone_path, timeout=8, term_grace=0.5) is True
        assert _count_pack_files(clone_path) == 1
        assert _ref_step_failures(emitted) == ["pack_refs"]
        stopped = "the ref steps' 4s of the repack's 8s timeout ran out during git"
        assert [
            r
            for r in records
            if r["level"].name == "WARNING" and f"{stopped} pack-refs" in r["message"]
        ]

    assert (state / "ready").exists(), "pack-refs never ran; test proves nothing"
    assert not (clone_path / ".git" / "packed-refs.lock").exists()
    assert not ref_lock.exists()
    assert git_fetcher._repack_lock_fds == set()

    remote = pygit2.Repository(str(tmp_path / "remote.git"))
    tip = _commit(remote, "package policy\n# after the stop\n", remote.head.target)
    remote.free()
    clone = pygit2.Repository(str(clone_path))
    clone.remotes["origin"].fetch(prune=pygit2.enums.FetchPrune.PRUNE)
    assert clone.references["refs/remotes/origin/master"].target == tip
    clone.free()
    monkeypatch.setenv("PATH", real_path)
    assert _repack_clone(clone_path, timeout=60) is True
    assert _loose_refs(clone_path) == []


def test_pack_refs_that_exits_0_but_leaves_the_refs_loose_is_counted(
    tmp_path, records, emitted
):
    """Git pack-refs exits 0 when it cannot remove a ref's own file (here a
    directory of refs the server cannot write to): what it said is a warning,
    and refs left in files of their own are counted as a failed pack-refs.

    Mutation: trusting the exit status leaves both unseen.
    """
    if os.geteuid() == 0:
        pytest.skip("root removes them anyway")
    clone_path, commits = _clone_with_fetch_packs(tmp_path, fetches=2)
    clone = pygit2.Repository(str(clone_path))
    for i in range(5):
        clone.create_reference(f"refs/remotes/origin/b{i}", commits[0])
    clone.free()
    stuck = clone_path / ".git" / "refs" / "remotes" / "origin"
    stuck.chmod(0o500)
    try:
        assert _repack_clone(clone_path, timeout=60) is True

        assert "refs/remotes/origin/b4" in _loose_refs(clone_path)
    finally:
        stuck.chmod(0o700)
    assert _count_pack_files(clone_path) == 1
    assert _ref_step_failures(emitted) == ["pack_refs"]
    warnings = [r["message"] for r in records if r["level"].name == "WARNING"]
    assert [m for m in warnings if "exited 0 but left 6 refs in files" in m]
    assert [m for m in warnings if "succeeded, and said" in m and "b4.lock" in m]


def test_a_repack_whose_git_outlives_its_stop_stays_recorded(
    tmp_path, monkeypatch, emitted
):
    """A git still running after its SIGKILL (stuck in uninterruptible I/O)
    may still write into the clone, so its locks stay, and so does the
    repack's record in the clone's lock file: the op that gets the lock once
    that git is gone removes what it left, and clears the record. A repack
    that ends cleanly clears its own. The ref step that ran past its share is
    counted as failed, though the repack ends there.

    Mutation: clearing the record whatever happened fails the first part; not
    clearing it after a clean repack fails the last; raising before counting
    fails the count.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    real_git = shutil.which("git")
    real_path = os.environ["PATH"]
    real_stop = git_fetcher._stop_repack
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'if [ "$3" = pack-refs ]; then\n'
        '  : > "$2/.git/packed-refs.lock"\n'
        "  while :; do /bin/sleep 1; done\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        refs_steps=True,
    )

    def _stop_that_cannot_tell(proc, grace, what):
        """Git is gone, but as a stop that timed out waiting reports it."""
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        return False

    monkeypatch.setattr(git_fetcher, "_stop_repack", _stop_that_cannot_tell)
    record = git_cli.clone_lock_path(clone_path)

    # A 4 s share for the ref steps: git config, then the pack-refs shim, start
    # within it on a loaded machine.
    with pytest.raises(TimeoutError):
        _repack_clone(clone_path, timeout=8, term_grace=0.5)

    assert _ref_step_failures(emitted) == ["pack_refs"]
    assert record.read_text().strip() == str(os.getpid())
    assert (clone_path / ".git" / "packed-refs.lock").exists()
    monkeypatch.setattr(git_fetcher, "_stop_repack", real_stop)
    monkeypatch.setenv("PATH", real_path)
    # That git is gone once nothing of its SIGKILLed group holds the lock.
    assert _wait_for(lambda: _clone_lock_is_free(clone_path))
    git_cli.clean_up_unfinished_op(clone_path)  # the next op on the clone
    assert record.read_text() == ""
    assert not (clone_path / ".git" / "packed-refs.lock").exists()
    assert _repack_clone(clone_path, timeout=60) is True
    assert record.read_text() == ""
    assert _loose_refs(clone_path) == []


def test_the_timeout_covers_the_ref_steps_and_the_repack_together(
    tmp_path, monkeypatch
):
    """One deadline for the whole repack, so that it still bounds how long the
    repack holds the clone's lock_source: a pack-refs that takes most of it
    leaves git repack only the rest.

    Mutation: giving each git command the full timeout lets this repack
    finish.
    """
    clone_path = _fake_clone(tmp_path)
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'if [ "$3" = pack-refs ]; then /bin/sleep 1.5; exit 0; fi\n'
        'if [ "$3" = config ]; then exit 0; fi\n'
        "/bin/sleep 1.5\n",
        refs_steps=True,
    )
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="timeout ran out during git repack"):
        _repack_clone(clone_path, timeout=2.5, term_grace=0.5)
    assert time.monotonic() - started < 2.5 + 0.5 + 1.0


def test_a_failed_pack_refs_is_a_warning_and_the_repack_still_runs(
    tmp_path, monkeypatch, records, emitted
):
    """A pack-refs killed by the kernel's OOM killer (a SIGKILL) leaves the
    refs loose and its locks behind; it is logged and counted, its locks go,
    since a git killed by a signal cannot remove its own, and git repack still
    merges the packs.

    Mutation: failing the repack on a failed pack-refs fails the return
    value and the pack count; not cleaning up after a signal leaves the lock;
    not counting it leaves a clone whose refs never get packed unseen.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    real_git = shutil.which("git")
    ref_lock = clone_path / ".git" / "refs" / "remotes" / "origin" / "master.lock"
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'if [ "$3" = pack-refs ]; then\n'
        '  : > "$2/.git/packed-refs.lock"\n'
        f'  : > "{ref_lock}"\n'
        "  kill -9 $$\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        refs_steps=True,
    )

    assert _repack_clone(clone_path, timeout=60) is True

    assert _count_pack_files(clone_path) == 1
    assert "refs/remotes/origin/master" in _loose_refs(clone_path)
    assert _lock_files(clone_path) == []
    [warning] = [
        r
        for r in records
        if r["level"].name == "WARNING" and "pack-refs" in r["message"]
    ]
    # sh, which runs git under the watchdog, reports a signal as 128 + its
    # number.
    assert f"status {128 + int(signal.SIGKILL)}" in warning["message"]
    assert _ref_step_failures(emitted) == ["pack_refs"]


def test_a_repack_leaves_a_clone_alone_while_a_fetch_holds_its_lock(tmp_path):
    """A git command-line fetch holds the clone's lock for as long as any
    process of its own runs. The repack raises GitCliBusyError then, having run
    nothing, so none of its ref steps touches the clone: its reflogs, its loose
    refs, its config and a packed-refs.lock that may be the fetch's all stay as
    they are.

    Mutation: running the ref steps before taking the clone's lock changes
    each of them.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    git_dir = clone_path / ".git"
    (git_dir / "packed-refs.lock").touch()
    before = (
        _reflogs(clone_path),
        _loose_refs(clone_path),
        _reflogs_setting(clone_path),
        _count_pack_files(clone_path),
    )
    fetch = git_cli.take_clone_lock(clone_path)
    assert fetch is not None
    try:
        with pytest.raises(git_cli.GitCliBusyError):
            _repack_clone(clone_path, timeout=60)

        after = (
            _reflogs(clone_path),
            _loose_refs(clone_path),
            _reflogs_setting(clone_path),
            _count_pack_files(clone_path),
        )
        assert after == before
        assert (git_dir / "packed-refs.lock").exists()
        assert not (git_dir / "packed-refs").exists()
    finally:
        git_cli.drop_clone_lock(fetch)
    assert git_fetcher._repack_lock_fds == set()


@pytest.mark.asyncio
async def test_a_fetch_leaves_a_running_repack_s_files_alone(tmp_path, monkeypatch):
    """The other way round: while git repack writes its temp packs (its
    ``.tmp-<pid>-pack-*`` and pack-objects' ``tmp_pack_*``), the repack holds
    the clone's lock, so a git command-line fetch is refused before its git
    runs, and none of its clean-up (after a failed or killed git) can reach
    them; a libgit2 fetch's clean-up of a dead op leaves the clone alone too.
    """
    clone_path, _ = _clone_with_fetch_packs(tmp_path, fetches=2)
    clone = pygit2.Repository(str(clone_path))
    clone.remotes.set_url("origin", (tmp_path / "remote.git").as_uri())
    clone.free()
    real_git = shutil.which("git")
    state = tmp_path / "state"
    state.mkdir()
    pack = _pack_dir(clone_path)
    live = [pack / ".tmp-77-pack-live.pack", pack / "tmp_pack_live"]
    _install_git_shim(
        tmp_path,
        monkeypatch,
        "".join(f': > "{p}"\n' for p in live)
        + f': > "{state}/ready"\n'
        + f'while [ ! -e "{state}/release" ]; do /bin/sleep 0.05; done\n'
        + f'exec "{real_git}" "$@"\n',
    )
    repack = asyncio.ensure_future(run_sync(_repack_clone, clone_path, 60))
    try:
        assert await _wait_for_async(lambda: (state / "ready").exists())
        source = GitPolicyScopeSource(
            source_type="git",
            url=(tmp_path / "remote.git").as_uri(),
            branch="master",
            auth=NoAuthData(),
        )

        with pytest.raises(git_cli.GitCliBusyError):
            await git_cli.cli_fetch(
                clone_path, "origin", source, prune=False, timeout=60
            )
        git_cli.clean_up_unfinished_op(clone_path)

        assert [p for p in live if not p.exists()] == []
    finally:
        (state / "release").touch()
    assert await repack is True
    assert _count_pack_files(clone_path) == 1


async def _clone_whose_pack_refs_was_killed(tmp_path, monkeypatch):
    """A scope clone whose refs are packed, with one loose ref, whose next
    repack died in pack-refs with its process (what a container's death does):
    the repacking process SIGKILLed, and with it git's whole group (by the
    watchdog the repack runs git under), and packed-refs.lock and a ref's lock
    left in the clone.

    Its remote has then deleted env2, so a fetch that prunes has to
    rewrite packed-refs, and fails while the lock is there. Prune is on
    from then on (on before, it would keep the refs loose:
    _packing_refs). Returns the scope and the ref's lock.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(2)
    scope.remote.create_reference("refs/heads/env2", scope.tip)
    await scope.sync()
    GitPolicyFetcher.forget_repo(str(scope.clone_path))
    assert _repack_clone(scope.clone_path, timeout=60) is True  # refs packed
    clone = scope.clone_path
    git_dir = clone / ".git"
    ref_lock = git_dir / "refs" / "remotes" / "origin" / "master.lock"
    # A ref the killed pack-refs was to pack, which the next one must.
    scope.remote.create_reference("refs/heads/env3", scope.tip)
    await scope.sync()
    assert _loose_refs(clone) == ["refs/remotes/origin/env3"]

    real_git = shutil.which("git")
    real_path = os.environ["PATH"]
    state = tmp_path / "state"
    state.mkdir()
    shim_dir = _install_git_shim(
        tmp_path,
        monkeypatch,
        'if [ "$3" = pack-refs ]; then\n'
        '  : > "$2/.git/packed-refs.lock"\n'
        f'  : > "{ref_lock}"\n'
        f'  echo $$ > "{state}/git.pid"\n'
        "  exec /bin/sleep 600\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        refs_steps=True,
    )
    monkeypatch.setenv("PATH", real_path)
    # The shim goes on the repacking process's PATH only after its imports:
    # importing GitPython runs `git version`.
    repacker = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os\n"
            "from opal_server.git_fetcher import _repack_clone\n"
            f"os.environ['PATH'] = {str(shim_dir)!r} + os.pathsep + os.environ['PATH']\n"
            f"_repack_clone({str(clone)!r}, timeout=600)\n",
        ],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        started = _wait_for(lambda: (state / "git.pid").exists())
    finally:
        repacker.kill()
        _, repacker_stderr = repacker.communicate()
    assert started, f"pack-refs never started: {repacker_stderr.decode()[-2000:]}"
    git_pid = int((state / "git.pid").read_text())
    assert _wait_gone(git_pid), "the watchdog did not take git with its process"
    assert (git_dir / "packed-refs.lock").exists() and ref_lock.exists()
    scope.remote.references.delete("refs/heads/env2")
    stuck = _git(
        clone,
        "fetch",
        "--prune",
        "--no-tags",
        "--no-auto-maintenance",
        "-q",
        "origin",
        check=False,
    )
    assert stuck.returncode != 0, "the premise: a pruning fetch fails on the lock"
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)
    # A git fetch of every branch, as the libgit2 one is, so that it prunes env2
    # (a fetch of the scope's branch alone prunes only that branch's refs).
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 0
    )
    return scope, ref_lock


@pytest.mark.asyncio
@pytest.mark.parametrize("restart", [True, False], ids=["restart", "no-restart"])
async def test_a_pack_refs_killed_with_its_process_costs_no_fetch_or_repack(
    tmp_path, monkeypatch, restart
):
    """A pack-refs killed with its process leaves its locks in the clone, with
    nothing left to remove them (see _clone_whose_pack_refs_was_killed).

    With a restart, the preload's sweep removes them, and the next fetch and
    the next repack succeed at once. Without one, the next repack removes them
    first (it holds the clone's lock), packs the refs, and the fetch after it
    succeeds.

    Mutation: not removing them when the repack starts fails "no-restart":
    its pack-refs fails on them and the ref it was to pack stays loose.
    """
    scope, ref_lock = await _clone_whose_pack_refs_was_killed(tmp_path, monkeypatch)
    clone = scope.clone_path
    git_dir = clone / ".git"

    def _repacked_at_once() -> None:
        assert _repack_clone(clone, timeout=60) is True
        assert not (git_dir / "packed-refs.lock").exists() and not ref_lock.exists()
        assert _loose_refs(clone) == []

    # The fetch that has to rewrite packed-refs, by git as the clone lock's
    # other holders run it.
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    if restart:
        git_fetcher.sweep_scope_clone_leftovers(tmp_path / "base")
    else:
        _repacked_at_once()
    tip = str(scope.push())
    await scope.sync()
    assert _refs(clone)["refs/remotes/origin/master"] == tip
    assert "refs/remotes/origin/env2" not in _refs(clone)
    assert scope.notified[-1][1] == tip
    if restart:
        _repacked_at_once()
    _git(clone, "fsck", "--no-progress")


@pytest.mark.asyncio
@pytest.mark.parametrize("cli", [True, False], ids=["git", "libgit2"])
async def test_a_pack_refs_killed_without_a_preload_costs_no_fetch(
    tmp_path, monkeypatch, cli
):
    """`opal-server run` has no preload, so after the restart nothing sweeps
    the clone, and a repack runs only after a fetch that succeeded: a pruning
    fetch that kept failing on the dead pack-refs' locks would keep the clone
    stale for good. The repack records itself in the clone's lock file, as
    git_cli's ops do, so the next fetch finds an op there that never finished
    and removes what it left first, with git or with libgit2; then the next
    repack packs the refs.

    Mutation: not recording the repack, or clearing the record before its
    git is gone, fails both; a libgit2 fetch that does not read the record
    fails "libgit2".
    """
    scope, ref_lock = await _clone_whose_pack_refs_was_killed(tmp_path, monkeypatch)
    clone = scope.clone_path
    git_dir = clone / ".git"
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    tip = str(scope.push())

    await scope.sync()

    assert _refs(clone)["refs/remotes/origin/master"] == tip
    assert "refs/remotes/origin/env2" not in _refs(clone)
    assert scope.notified[-1][1] == tip
    assert not (git_dir / "packed-refs.lock").exists() and not ref_lock.exists()
    GitPolicyFetcher.forget_repo(str(clone))
    # Off, so that the ref steps pack the refs with libgit2 too (_packing_refs).
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", False)
    assert _repack_clone(clone, timeout=60) is True
    assert _loose_refs(clone) == []
    _git(clone, "fsck", "--no-progress")
