"""The scope-clone repack primitive: ``_count_pack_files`` and
``_repack_clone``.

The repository tests use real git: a bare remote and a libgit2 clone of it,
the way the scopes fetcher builds its clones. A libgit2 clone of a local path
starts with loose objects, and every fetch after it writes exactly one new pack
that nothing ever merges; that growth is what the repack exists to undo.

The process-control tests put a ``git`` shim on PATH instead, because a real
repack cannot be made to hang on cue.
"""

import math
import os
import stat
import subprocess
import time
from pathlib import Path

import pygit2
import pytest
from opal_server import git_fetcher
from opal_server.config import OpalServerConfig, opal_server_config
from opal_server.git_fetcher import (
    GitRepackError,
    _count_pack_files,
    _repack_clone,
    _repack_timeout_seconds,
)

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
    """A clone dir with a real-looking pack and two pre-existing temp files."""
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


@pytest.mark.parametrize("ignores_term", [False, True], ids=["term", "kill"])
def test_timeout_stops_git_and_removes_its_temp_packs(
    tmp_path, monkeypatch, ignores_term
):
    """A repack past its timeout is stopped with its whole process group, and
    the temp files git left in the pack dir are removed; nothing else is.

    The shim leaves what a killed repack leaves (pack-objects' ``tmp_pack_*``
    and repack's ``.tmp-<pid>-pack-*``), plus a file named like libgit2's
    indexer temp, and runs a background child standing in for pack-objects.
    In the "kill" case the shim traps SIGTERM and its child ignores it, so
    only the SIGKILL fallback after the grace period ends them.
    """
    clone_path = _fake_clone(tmp_path)
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
        f': > "$pack/pack_git2_Zz9Yy8"\n'
        f'echo $$ > "{state}/leader.pid"\n'
        f"{child}\n"
        f'echo $! > "{state}/child.pid"\n' + tail,
    )
    timeout, grace = 1.0, (0.3 if ignores_term else 5.0)

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
        "tmp_pack_stale",  # there before this repack started: not its temp
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
    assert "tmp_pack_Qw3Er4" not in os.listdir(_pack_dir(clone_path))
    assert "tmp_pack_stale" in os.listdir(_pack_dir(clone_path))


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
        with pytest.raises(FileNotFoundError):
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
