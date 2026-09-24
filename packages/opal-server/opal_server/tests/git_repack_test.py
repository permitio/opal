"""The scope-clone repack: the primitive (``_count_pack_files``,
``_repack_clone``), the repack lock it runs under, its wiring into the scope
sync (``GitPolicyFetcher._maybe_repack``), and the GitPython handles on scope
clones that must be closed for a repack's deleted packs to free their disk.

The repository tests use real git: a bare remote and a libgit2 clone of it,
the way the scopes fetcher builds its clones. A libgit2 clone of a local path
starts with loose objects, and every fetch after it writes exactly one new pack
that nothing ever merges; that growth is what the repack exists to undo.

The process-control tests put a ``git`` shim on PATH instead, because a real
repack cannot be made to hang on cue.
"""

import asyncio
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
import pygit2
import pytest
from opal_common.async_utils import run_sync
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
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
from opal_server.scopes.service import NewCommitsCallbacks

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


def _lock_is_free(path: Path) -> bool:
    """Whether the repack lock at ``path`` can be taken, probing it the way
    another process would: through an open file of its own."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
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
    # Unindexed too, but there before this repack: not known to be its own.
    (_pack_dir(clone_path) / "pack-cccc.pack").write_bytes(b"x")
    state = tmp_path / "state"
    state.mkdir()
    if ignores_term:
        child = "( trap '' TERM; exec /bin/sleep 30 ) &"
        tail = (
            f"trap 'echo TERM >> \"{state}/signals\"' TERM\n"
            f': > "{state}/ready"\n'
            "while :; do /bin/sleep 1; done\n"
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
    timeout, grace = 3.0, (0.3 if ignores_term else 5.0)

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
        "pack-cccc.pack",
        "pack_git2_Zz9Yy8",  # libgit2's name: never ours to delete
        "pack_git2_old",
    ]  # tmp_pack_stale went before git started: see the next test
    assert git_fetcher._repack_lock_fds == set()
    assert _lock_is_free(git_fetcher._repack_lock_path(clone_path))


def test_leftovers_of_a_dead_repack_are_removed_before_git_runs(tmp_path, monkeypatch):
    """Under the repack lock no other repack is alive, so every git temp file
    in the pack dir was left by one that died, say one orphaned by a killed
    leader and later killed itself, and nothing else ever removes it.

    Packs stay, an unindexed one included: only a repack's OWN unindexed
    pack is known to be garbage.
    """
    clone_path = _fake_clone(tmp_path)
    pack = _pack_dir(clone_path)
    for name in (".tmp-999-pack-dead.pack", ".tmp-999-pack-dead.idx", "pack-cccc.pack"):
        (pack / name).write_bytes(b"x")
    seen = tmp_path / "seen"
    _install_git_shim(
        tmp_path, monkeypatch, f'ls -1A "$2/.git/objects/pack" > "{seen}"\n'
    )

    assert _repack_clone(clone_path, timeout=60) is True

    assert sorted(seen.read_text().split()) == [
        "pack-aaaa.idx",
        "pack-aaaa.pack",
        "pack-cccc.pack",
        "pack_git2_old",
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
    tmp_path, monkeypatch
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


def test_unindexed_pack_stays_once_the_lock_file_was_replaced(tmp_path, monkeypatch):
    """With the lock file deleted while held, a repack started since may have
    locked a new one and be installing a pack in this clone right now, so a
    ``.pack`` without its ``.idx`` is no longer known to be garbage and is left
    alone.

    Temp files still go: a repack that loses one fails before it
    deletes any old pack.
    """
    clone_path = _fake_clone(tmp_path)
    _install_git_shim(
        tmp_path,
        monkeypatch,
        'pack="$2/.git/objects/pack"\n'
        f'rm -f "$2/../{git_fetcher._REPACK_LOCK_FILE}"\n'
        ': > "$pack/pack-bbbb.pack"\n: > "$pack/tmp_pack_Rt5Yu6"\n'
        "exit 3\n",
    )
    with pytest.raises(GitRepackError):
        _repack_clone(clone_path, timeout=60)
    names = os.listdir(_pack_dir(clone_path))
    assert "pack-bbbb.pack" in names
    assert "tmp_pack_Rt5Yu6" not in names


# --- the repack lock -------------------------------------------------------------


def test_one_lock_for_every_clone_in_the_directory(tmp_path):
    assert git_fetcher._repack_lock_path(
        tmp_path / "a"
    ) == git_fetcher._repack_lock_path(tmp_path / "b")


def test_repack_is_skipped_while_another_repack_holds_the_lock(tmp_path, monkeypatch):
    """Another process's repack, of any clone next to this one, means this
    one does not run at all: skipped, not waited for, and not swept."""
    clone_path = _fake_clone(tmp_path)
    runs = tmp_path / "runs"
    _install_git_shim(tmp_path, monkeypatch, f'echo run >> "{runs}"\n')
    lock = git_fetcher._repack_lock_path(clone_path)
    held = os.open(lock, os.O_RDWR | os.O_CREAT)  # its own open file, as in
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another process
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
    lock = git_fetcher._repack_lock_path(clone_path)
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
    lock = tmp_path / git_fetcher._REPACK_LOCK_FILE
    fd = git_fetcher._take_repack_lock(lock)
    assert fd is not None
    to_child_r, to_child_w = os.pipe()
    to_parent_r, to_parent_w = os.pipe()
    pid = os.fork()
    if pid == 0:  # the forked child: report, then live on until told
        try:
            try:
                os.fstat(fd)
                closed = 0
            except OSError:
                closed = 1
            still_locked = 0 if _lock_is_free(lock) else 1
            os.write(to_parent_w, b"%d%d" % (closed, still_locked))
            select.select([to_child_r], [], [], 10)
        finally:
            os._exit(0)
    try:
        report = os.read(to_parent_r, 2)
        assert report == b"11", "child kept its copy (1st) or unlocked it (2nd)"
        git_fetcher._drop_repack_lock(fd)
        # The child is still alive, and holds nothing.
        assert _lock_is_free(lock), "the forked child still holds the lock"
    finally:
        if fd in git_fetcher._repack_lock_fds:
            git_fetcher._drop_repack_lock(fd)
        os.write(to_child_w, b"x")
        os.waitpid(pid, 0)
        for end in (to_child_r, to_child_w, to_parent_r, to_parent_w):
            os.close(end)


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
def test_missing_git_raises_file_not_found(tmp_path, monkeypatch, kind):
    """No git on PATH is FileNotFoundError, whatever else PATH holds.

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
        (0, 300.0),
        (-1.0, 300.0),
        (math.nan, 300.0),
        (math.inf, 300.0),
        (-math.inf, 300.0),
    ],
)
def test_repack_timeout_seconds_never_means_no_limit(monkeypatch, configured, expected):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_TIMEOUT", configured)
    assert _repack_timeout_seconds() == expected


def test_repack_default_timeout_matches_the_config_default(monkeypatch):
    monkeypatch.delenv("OPAL_SCOPES_GIT_REPACK_TIMEOUT", raising=False)
    clean = OpalServerConfig(prefix="OPAL_")
    assert (
        git_fetcher._REPACK_DEFAULT_TIMEOUT_SECONDS == clean.SCOPES_GIT_REPACK_TIMEOUT
    )


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
# pack, so with the limit at 3 the third fetch is the one that repacks.

_LIMIT = 3


@pytest.fixture(autouse=True)
def _clean_fetcher_state(monkeypatch):
    """Limit 3, and a clean slate of the per-process state the sync keeps: the
    fetcher's class-level caches (as invalid_repo_recovery_test does) and the
    repack's failure cooldowns and git-missing latch."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", _LIMIT)
    monkeypatch.setattr(git_fetcher, "_repack_git_missing", False)
    monkeypatch.setattr(git_fetcher, "_repack_failed_at", {})
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


@pytest.fixture
def records():
    captured = []
    sink = logger.add(lambda m: captured.append(m.record), level="DEBUG")
    yield captured
    logger.remove(sink)


class _RepackSpy:
    """Stands in for ``_repack_clone``: records each call, then optionally
    blocks until ``gate`` opens, then raises ``raises`` or runs the real
    repack."""

    def __init__(self, raises: BaseException | None = None, gate=None):
        self.raises = raises
        self.gate = gate
        self.calls: list = []
        self.started = threading.Event()

    def __call__(self, repo_path, timeout, **kwargs):
        self.calls.append(os.fspath(repo_path))
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
        kwargs.setdefault("force_fetch", True)
        await self.fetcher.fetch_and_notify_on_changes(**kwargs)

    async def push_and_sync(self) -> str:
        tip = self.push()
        await self.sync()
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
    tmp_path, emitted, records
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

    # The next sync reopens the clone and both it and a bundle serve the
    # newest commit, full and as a diff against the pre-repack tip.
    newest = await scope.push_and_sync()
    assert scope.notified[-1][:2] == (tip, newest)
    assert path in GitPolicyFetcher.repos
    assert scope.fetcher.make_bundle().hash == newest
    diff = await run_sync(scope.fetcher.make_bundle, tip)
    assert (diff.old_hash, diff.hash) == (tip, newest)
    assert _repack_outcomes(emitted) == ["ok"]  # 2 packs now: nothing to do


@pytest.mark.asyncio
async def test_repack_holds_lock_source_so_a_second_sync_of_the_clone_waits(
    tmp_path, monkeypatch
):
    """The repack runs under the fetching sync's lock_source.

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
async def test_repack_running_in_another_process_is_a_skip(tmp_path, emitted, records):
    """A previous leader's orphaned git (any repack another process runs next
    to this clone) holds the repack lock: the sync skips, reports nothing as
    done and keeps its handle, and a later fetch repacks once it is gone."""
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    path = str(scope.clone_path)
    lock = git_fetcher._repack_lock_path(scope.clone_path)
    held = os.open(lock, os.O_RDWR | os.O_CREAT)  # another process's open file
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        tip = await scope.push_and_sync()
        assert scope.notified[-1][1] == tip
        assert _count_pack_files(scope.clone_path) == _LIMIT
        assert _repack_outcomes(emitted) == []
        assert not [r for r in records if r["message"].startswith("Repacked")]
        assert path in GitPolicyFetcher.repos, "nothing was repacked: keep it"
        assert git_fetcher._repack_failed_at == {}  # a skip is not a failure
    finally:
        os.close(held)

    await scope.push_and_sync()
    assert _count_pack_files(scope.clone_path) == 1
    assert _repack_outcomes(emitted) == ["ok"]


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
async def test_only_a_fetch_made_by_this_sync_triggers_a_repack(tmp_path, monkeypatch):
    """A sync that fetched nothing added no pack (phase 2 of a pass), and a
    fetch that failed raised before the housekeeping; neither repacks, even
    with the clone already at the limit."""
    spy = _RepackSpy()
    monkeypatch.setattr(git_fetcher, "_repack_clone", spy)
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", _LIMIT - 1)

    await scope.sync(force_fetch=False)  # the branch is there: no fetch
    assert spy.calls == []

    scope.remote.free()
    os.rename(tmp_path / "s1.git", tmp_path / "gone.git")
    with pytest.raises(pygit2.GitError):
        await scope.sync()
    assert spy.calls == []
    assert _count_pack_files(scope.clone_path) == _LIMIT - 1


@pytest.mark.parametrize(
    "exc, outcome",
    [
        (GitRepackError(128, "fatal: no space left on device"), "error"),
        (TimeoutError("git repack exceeded 300.0s"), "timeout"),
        # Not "git is missing": the clones' dir vanished under the lock file.
        (FileNotFoundError(errno.ENOENT, "No such file", ".opal-repack.lock"), "error"),
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
    """``-a -d`` drops what nothing references, and a PDP's diff base may be a
    commit a force-push took off the branch.

    The reflogs keep it.
    """
    scope = _ScopeRepo(tmp_path, "s1")
    await scope.fetched(_LIMIT - 2)
    base = scope.tip
    old_tip = await scope.push_and_sync()
    assert _count_pack_files(scope.clone_path) == _LIMIT - 1

    new_tip = str(scope.force_push(onto=base))
    await scope.sync()  # force-updates origin/master, then repacks

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
