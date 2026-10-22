"""The scope-clone repack: the primitive (``_count_pack_files``,
``_repack_clone``), the repack lock it runs under, its wiring into the scope
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
import signal
import stat
import subprocess
import sys
import threading
import time
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
from opal_server import git_fetcher
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

_SIG = pygit2.Signature("opal-test", "opal-test@example.com")


def _commit(repo: pygit2.Repository, content: str, parent=None) -> pygit2.Oid:
    blob = repo.create_blob(content.encode())
    builder = repo.TreeBuilder()
    builder.insert("policy.rego", blob, pygit2.GIT_FILEMODE_BLOB)
    parents = [parent] if parent is not None else []
    return repo.create_commit(
        "refs/heads/master", _SIG, _SIG, content, builder.write(), parents
    )


def _clone_with_fetch_packs(tmp_path: Path, fetches: int):
    """A libgit2 clone holding one pack per fetch, plus every commit id."""
    remote = pygit2.init_repository(str(tmp_path / "remote.git"), bare=True)
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
        builder.insert("policy.rego", blob, pygit2.GIT_FILEMODE_BLOB)
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
    assert (
        _git(clone_path, "cat-file", "-t", landing, check=False).returncode == 0
    ), "the repack deleted an object a landing fetch is about to point a ref at"
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


def _install_git_shim(tmp_path: Path, monkeypatch, body: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    shim.write_text("#!/bin/sh\n" + body)
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


@pytest.mark.parametrize("ignores_term", [False, True], ids=["term", "kill"])
def test_timeout_stops_git_and_removes_its_temp_packs(
    tmp_path, monkeypatch, ignores_term
):
    """A repack past its timeout is stopped with its whole process group, and
    what it left in the pack dir is removed; nothing else is.

    The shim leaves what a killed repack leaves (pack-objects' ``tmp_pack_*``,
    repack's ``.tmp-<pid>-pack-*``, and a ``.pack`` installed without its
    ``.idx``: git renames the ``.pack`` first and the ``.idx`` last), plus a
    file named like libgit2's indexer temp, and runs a background child
    standing in for pack-objects. In the "kill" case the shim traps SIGTERM
    and its child ignores it, so only the SIGKILL fallback after the grace
    period ends them.
    """
    clone_path = _fake_clone(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    if ignores_term:
        child = "( trap '' TERM; exec /bin/sleep 30 ) &"
        # `sleep & wait`, not a foreground `sleep`: bash runs a trap only
        # once its foreground command returns, and a `sleep 1` forked just
        # after the group SIGTERM never got it, so the trap could wait out
        # that whole second, past the 0.3 s grace, and SIGKILL landed first
        # (seen on a CI runner). The `wait` builtin returns at once on a
        # trapped signal.
        tail = (
            f"trap 'echo TERM >> \"{state}/signals\"' TERM\n"
            f': > "{state}/ready"\n'
            "while :; do /bin/sleep 1 & wait $!; done\n"
        )
    else:
        child = "/bin/sleep 30 &"
        tail = f': > "{state}/ready"\nwait\n'
    _install_git_shim(
        tmp_path,
        monkeypatch,
        f'pack="$2/.git/objects/pack"\n'
        f': > "$pack/tmp_pack_Ab12Cd"\n'
        f': > "$pack/.tmp-$$-pack-0123abcd.pack"\n'
        f': > "$pack/.tmp-$$-pack-0123abcd.idx"\n'
        f': > "$pack/pack-0123abcd.pack"\n'
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
    assert not _pid_alive(leader), "git itself still running"
    assert _wait_gone(child_pid), "git's child (pack-objects) still running"
    if ignores_term:
        assert (state / "signals").read_text().split() == ["TERM"]
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


def test_leftovers_of_a_dead_repack_are_removed_before_git_runs(tmp_path, monkeypatch):
    """Under the repack lock no other repack is alive, so every git temp file
    in the pack dir, and every pack without its index, was left by one that
    died, say one orphaned by a killed leader and later killed itself, and
    nothing else ever removes it.

    libgit2's files stay: its in-flight names, and a fetched pack's ``.idx``
    committed before its ``.pack`` (measured on libgit2 1.7.2).
    """
    clone_path = _fake_clone(tmp_path)
    pack = _pack_dir(clone_path)
    for name in (
        ".tmp-999-pack-dead.pack",
        ".tmp-999-pack-dead.idx",
        "pack-cccc.pack",  # killed between git's two renames
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
    for name in ("pack-eeee.pack", "pack-eeee.idx", "pack-ffff.pack"):
        (pack / name).write_bytes(b"x")
    real_names = git_fetcher._pack_dir_names
    monkeypatch.setattr(
        git_fetcher,
        "_pack_dir_names",
        lambda path: real_names(path) - {"pack-eeee.idx"},
    )

    git_fetcher._remove_repack_leftovers(pack, "in this test")

    assert sorted(os.listdir(pack)) == ["pack-eeee.idx", "pack-eeee.pack"]


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
    """No lock file: nothing an orphan sweep of the clones directory could
    delete, and so let a second repack in."""
    clones_dir = tmp_path / "git_sources"
    _pack_dir(clones_dir / "clone").mkdir(parents=True)
    _install_git_shim(tmp_path, monkeypatch, "exit 0\n")
    assert _repack_clone(clones_dir / "clone", timeout=60) is True
    assert os.listdir(clones_dir) == ["clone"]


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


def test_the_lock_outlives_the_process_that_started_git(tmp_path, monkeypatch):
    """A leader SIGKILLed mid-repack (gunicorn's WORKER TIMEOUT) leaves git
    running in its own session.

    Git holds the lock through the fd it was handed, and so does every
    child that inherited it (a stand-in for pack-objects here), so the
    next leader's repack is skipped until they have all exited, and then
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
        assert _pid_alive(git_pid), "git died with the process that started it"
        assert not _lock_is_free(
            lock
        ), "the lock died with the process that started git"

        assert _repack_clone(clone_path, timeout=60) is False
        assert len((state / "runs").read_text().split()) == 1
    finally:
        (state / "release").touch()
    assert _wait_gone(child_pid) and _wait_gone(git_pid)
    assert _lock_is_free(lock)
    assert _repack_clone(clone_path, timeout=60) is True
    assert len((state / "runs").read_text().split()) == 2


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")
# Python 3.12+ warns on fork() with threads alive, as it would in the gunicorn
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

    "unsearchable-dir" is the official image's case: its PATH lists
    /root/.local/bin, which the opal user cannot search, and a bare exec
    lookup then reports the EACCES from that entry (PermissionError)
    instead of "not found".
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
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    assert not git_fetcher._repack_lock.locked(), "a test leaked a running repack"
    assert git_fetcher._repack_lock_fds == set(), "a test leaked a repack lock fd"


@pytest.fixture
def emitted(monkeypatch):
    """Capture calls through the metrics facade (metrics_emission_test's
    pattern: every emitting module shares the one ``metrics`` module)."""
    calls = {"gauge": [], "increment": []}
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
    return calls


def _repack_outcomes(calls) -> list:
    return [
        tags["outcome"]
        for metric, tags in calls["increment"]
        if metric == "opal_server.scopes.git_repack"
    ]


def _repack_seconds(calls) -> list:
    return [
        (value, tags)
        for metric, value, tags in calls["gauge"]
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
    """Stands in for ``_repack_clone``: records each call, runs ``on_start``,
    then optionally blocks until ``gate`` opens, then raises ``raises`` or runs
    the real repack."""

    def __init__(self, raises: BaseException | None = None, gate=None, on_start=None):
        self.raises = raises
        self.gate = gate
        self.on_start = on_start
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
        return _repack_clone(repo_path, timeout, **kwargs)


class _ScopeRepo:
    """A bare remote the test pushes to, and a scope fetcher syncing it.

    ``notified`` records every ``on_update`` as (old head, new head, pack
    count of the clone at that moment).
    """

    def __init__(self, tmp_path: Path, name: str):
        remote_path = tmp_path / f"{name}.git"
        self.remote = pygit2.init_repository(str(remote_path), bare=True)
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
        builder.insert("policy.rego", blob, pygit2.GIT_FILEMODE_BLOB)
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
    assert (
        path not in GitPolicyFetcher.repos
    ), "the cached handle was kept, holding the deleted packs open"
    assert freed == [path], "the cached handle was dropped but not free()'d"
    assert _repack_outcomes(emitted) == ["ok"]
    [(seconds, tags)] = _repack_seconds(emitted)
    assert seconds >= 0
    assert tags == {"pid": str(os.getpid()), "outcome": "ok"}
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
    assert tags == {"pid": str(os.getpid()), "outcome": outcome}
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

    # Once the hour is up it is tried again.
    git_fetcher._repack_failed_at[
        scope.source_id
    ] -= git_fetcher._REPACK_FAILURE_COOLDOWN_SECONDS
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
    no_git = tmp_path / "no-git"
    no_git.mkdir()
    monkeypatch.setenv("PATH", str(no_git))  # the real primitive, finding no git
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    first = _ScopeRepo(tmp_path, "s1")
    second = _ScopeRepo(tmp_path, "s2")
    await first.fetched(_LIMIT - 1)
    await second.fetched(_LIMIT - 1)

    tip = await first.push_and_sync()

    assert first.notified[-1][1] == tip
    assert spy.calls == [str(first.clone_path)]
    assert _repack_outcomes(emitted) == ["git_missing"]
    assert _repack_seconds(emitted) == []  # nothing ran, so no duration
    [error] = [r for r in records if r["level"].name == "ERROR"]
    assert "git" in error["message"]

    await second.push_and_sync()  # another clone, same process: still off
    await first.push_and_sync()
    assert spy.calls == [str(first.clone_path)]
    assert _repack_outcomes(emitted) == ["git_missing"]
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
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_TIMEOUT", 0.2)
    monkeypatch.setattr(git_fetcher, "_REPACK_EXECUTOR_SLACK_SECONDS", 0.1)
    gate = threading.Event()
    spy = _RepackSpy(gate=gate)  # stuck where no timeout of ours reaches
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    first = _ScopeRepo(tmp_path, "s1")
    second = _ScopeRepo(tmp_path, "s2")
    await first.fetched(_LIMIT - 1)
    await second.fetched(_LIMIT - 1)
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
        if func is git_fetcher._repack_clone_exclusive and refusals:
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
async def test_refresh_marks_the_repack_due_and_the_next_pass_runs_it_once(
    tmp_path, monkeypatch, emitted
):
    """A refresh (POST /scopes/{id}/refresh, a PUT) syncs its scope outside any
    pass, the way the watcher's trigger does: the fetch marks the clone due and
    repacks nothing.

    The next pass repacks it, once, and clears the mark.
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


def test_preload_marks_the_repack_due_and_the_first_pass_runs_it(tmp_path, monkeypatch):
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
    monkeypatch.setattr(task_module, "RedisDB", lambda url: None)
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


def test_forked_child_starts_with_the_single_flight_free():
    """A repack thread running in the parent at fork does not exist in the
    child, so nothing there could release the lock it inherited held."""
    held = git_fetcher._repack_lock
    assert held.acquire(blocking=False)
    try:
        git_fetcher._reset_git_executor_after_fork()
        assert not git_fetcher._repack_lock.locked()
    finally:
        if held.locked():
            held.release()


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
