"""The git command-line fetch and clone (``opal_server.git_cli``), with real
git against local remotes: ``file://`` origins, a ``git http-backend`` server
on localhost that can stall in the middle of a pack, a TCP endpoint that never
answers, one that drips its answer in forever, and an sshd where one can be
started. Nothing here leaves localhost.
"""

import asyncio
import base64
import ctypes
import errno
import io
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import pygit2
import pytest
from opal_common.logger import logger
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    NoAuthData,
    SSHAuthData,
)
from opal_server import git_cli
from opal_server.config import opal_server_config
from opal_server.git_cli import (
    GitCliError,
    GitCliLocalError,
    GitCliRefusedSourceError,
    GitCliTimeoutError,
    cli_clone,
    cli_fetch,
    clone_lock_path,
    kill_grace_seconds,
    known_hosts_file,
    validate_git_cli_settings,
)
from opal_server.git_fetcher import GitCallback
from opal_server.tests.git_repack_test import _flock_fails_with

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

_TIMEOUT = 0.5
_GRACE = 0.5  # _short_grace
# For the tests that watch a hung op's processes: long enough for every one of
# them to show up in a sampling of the process table, even on a loaded machine.
_HUNG_TIMEOUT = 2.0


class _Gone:
    """An on_gone that records its call."""

    def __init__(self) -> None:
        self.calls = []
        self.event = asyncio.Event()

    def __call__(self, succeeded: Optional[bool]) -> None:
        self.calls.append(succeeded)
        self.event.set()

    async def wait(self, timeout: float = 30) -> None:
        await asyncio.wait_for(self.event.wait(), timeout)


def _source(url: str, auth=None) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=auth or NoAuthData(auth_type="none"),
    )


@pytest.fixture(autouse=True)
def _short_grace(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", _GRACE)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)


def _refs(path: Path, prefix: str = "refs/remotes/") -> dict:
    repo = pygit2.Repository(str(path))
    try:
        return {
            name: str(repo.references[name].resolve().target)
            for name in repo.references
            if name.startswith(prefix) and not name.endswith("/HEAD")
        }
    finally:
        repo.free()


def _remote_urls(path: Path) -> list:
    repo = pygit2.Repository(str(path))
    try:
        return [(r.name, r.url) for r in repo.remotes]
    finally:
        repo.free()


async def _clone(
    url: str, dest: Path, source=None, timeout: float = 60, on_gone=None
) -> None:
    await cli_clone(
        url,
        dest,
        source or _source(url),
        remote="origin",
        timeout=timeout,
        on_gone=on_gone,
    )


async def _fetch(
    clone: Path, source, prune=False, timeout: float = 60, on_gone=None
) -> None:
    await cli_fetch(
        clone, "origin", source, prune=prune, timeout=timeout, on_gone=on_gone
    )


def _point_at(clone: Path, url: str) -> None:
    repo = pygit2.Repository(str(clone))
    try:
        repo.remotes.set_url("origin", url)
    finally:
        repo.free()


def _leftovers(clone: Path) -> list:
    git_dir = clone / ".git"
    found = [
        str(p.relative_to(git_dir))
        for p in git_dir.rglob("*")
        if p.name.endswith(".lock") or p.name.startswith("tmp_")
    ]
    return sorted(found)


def _fsck(clone: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(clone), "fsck", "--no-progress", "--no-dangling"],
        capture_output=True,
        text=True,
    )


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def _shim(tmp_path: Path, monkeypatch, name: str, body: str) -> Path:
    """Put an executable ``name`` that runs ``body`` (sh) first on PATH; the
    file it creates first thing, to tell that it ran."""
    shims = tmp_path / "bin"
    shims.mkdir(exist_ok=True)
    path = shims / name
    started = shims / f"{name}.started"
    path.write_text(f"#!/bin/sh\n: > '{started}'\n{body}\n")
    path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    return started


# Long enough for git to have started a shim before it is stopped, even on a
# slow, loaded CI runner; the shim blocks git for good, so the timeout is what
# stops it.
_SHIM_TIMEOUT = 10.0


async def _run_and_watch(coro, marker, processes_with):
    """Run ``coro`` while sampling, over and over, the processes whose command
    line holds ``marker``; the finished task, every process seen, and the time
    taken."""
    loop = asyncio.get_running_loop()
    seen = set()
    task = asyncio.ensure_future(coro)
    start = time.monotonic()
    while not task.done():
        seen.update(await loop.run_in_executor(None, processes_with, marker))
        await asyncio.wait({task}, timeout=0.02)
    return task, seen, time.monotonic() - start


# --- the layout: what the scopes fetcher reads with pygit2 ---------------------


@pytest.mark.asyncio
async def test_a_clone_is_laid_out_like_a_libgit2_clone(git_origin, tmp_path):
    """Same remote and URL, same refs/remotes/origin/*, and an EMPTY
    FETCH_HEAD: measured with pygit2 1.21.0 / libgit2 1.9.7, a libgit2 clone
    writes an empty FETCH_HEAD, while ``git clone`` writes none at all. No
    reflog is written for the clone's refs."""
    libgit2 = tmp_path / "libgit2"
    pygit2.clone_repository(git_origin.url, str(libgit2)).free()
    cli = tmp_path / "cli"

    await _clone(git_origin.url, cli)

    assert _refs(cli) == _refs(libgit2)
    assert set(_refs(cli)) == {
        "refs/remotes/origin/master",
        "refs/remotes/origin/dev",
        "refs/remotes/origin/feature/x",
    }
    for clone in (libgit2, cli):
        assert (clone / ".git" / "FETCH_HEAD").read_text() == ""
    assert _remote_urls(cli) == [("origin", git_origin.url)]
    repo = pygit2.Repository(str(cli))
    try:
        assert list(repo.remotes["origin"].fetch_refspecs) == [
            "+refs/heads/*:refs/remotes/origin/*"
        ]
    finally:
        repo.free()
    assert not (cli / ".git" / "logs" / "refs" / "remotes").exists()
    # The directory it was cloned into was renamed, and no hook was copied in.
    assert not (cli / ".git" / "hooks").exists()
    # Beside the clone only its lock file, which records no op under way.
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".")) == [
        ".cli.lock"
    ]
    assert clone_lock_path(cli).read_bytes() == b""
    assert _fsck(cli).returncode == 0


@pytest.mark.asyncio
async def test_a_clone_s_config_says_once_that_no_reflog_is_written(
    git_origin, tmp_path
):
    """The init a clone runs writes core.logAllRefUpdates=true where the
    setting is unset; the clone's config holds false alone, which a plain `git
    config` can then set again (it fails on a key set twice)."""
    cli = tmp_path / "cli"

    await _clone(git_origin.url, cli)

    values = subprocess.run(
        ["git", "-C", str(cli), "config", "--get-all", "core.logAllRefUpdates"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert values == ["false"]


@pytest.mark.asyncio
async def test_a_clone_keeps_the_exact_source_url_credentials_and_all(
    git_http, make_origin, tmp_path
):
    """Git is given the URL without its user and password, yet the clone's
    remote must be the source's URL as it is, as a libgit2 clone has it:

    the fetcher checks the clone against it, and a mismatch would make
    it delete and clone the source again on every sync.
    """
    make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git", userinfo="alice:p%40ss")
    git_http.authorization = _basic("alice", "p@ss")

    await _clone(url, tmp_path / "cli")

    assert _remote_urls(tmp_path / "cli") == [("origin", url)]


@pytest.mark.asyncio
async def test_a_fetch_updates_fetch_head_and_the_refs_a_libgit2_fetch_updates(
    git_origin, tmp_path
):
    """FETCH_HEAD is rewritten, empty: nothing in OPAL reads what it holds,
    only its age."""
    libgit2 = tmp_path / "libgit2"
    pygit2.clone_repository(git_origin.url, str(libgit2)).free()
    cli = tmp_path / "cli"
    await _clone(git_origin.url, cli)
    fetch_head = cli / ".git" / "FETCH_HEAD"
    os.utime(fetch_head, (1_000_000, 1_000_000))
    git_origin.commit("master")
    git_origin.branch("new-branch")
    git_origin.delete("dev")

    repo = pygit2.Repository(str(libgit2))
    repo.remotes["origin"].fetch(prune=pygit2.enums.FetchPrune.PRUNE)
    repo.free()
    await _fetch(cli, _source(git_origin.url), prune=True)

    assert _refs(cli) == _refs(libgit2)
    assert "refs/remotes/origin/new-branch" in _refs(cli)
    assert "refs/remotes/origin/dev" not in _refs(cli)
    assert fetch_head.stat().st_mtime > time.time() - 60
    assert fetch_head.read_bytes() == b""


@pytest.mark.parametrize("offset", [-7200, 3600], ids=["past", "future"])
@pytest.mark.asyncio
async def test_a_fetch_with_nothing_new_dates_fetch_head_now(
    offset, git_origin, tmp_path
):
    """The probes read FETCH_HEAD's age: a fetch that brought nothing is still
    a fetch that succeeded, whenever FETCH_HEAD was dated (a clock that jumped
    either way).

    FETCH_HEAD is empty already: the open that empties it again dates
    it (O_TRUNC, by POSIX).
    """
    cli = tmp_path / "cli"
    await _clone(git_origin.url, cli)
    fetch_head = cli / ".git" / "FETCH_HEAD"
    assert fetch_head.read_bytes() == b""
    dated = time.time() + offset
    os.utime(fetch_head, (dated, dated))

    await _fetch(cli, _source(git_origin.url))

    assert abs(time.time() - fetch_head.stat().st_mtime) < 60


@pytest.mark.asyncio
async def test_a_fetch_git_fails_on_leaves_none_of_the_pack_it_was_writing(
    git_origin, tmp_path, monkeypatch
):
    """Git ends with an error of its own (here a full disk) with the pack it
    was writing still in temp files, which would keep the disk full and every
    later fetch failing; its locks it rolls back itself.

    Those temp files go, and so does a .keep it wrote with no pack to go
    with it; a .keep of a complete pack stays with it, and nothing that
    was there before the op goes. The next fetch, with room again,
    succeeds.
    """
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    pack_dir = clone / ".git" / "objects" / "pack"
    [complete] = [p.stem for p in pack_dir.glob("pack-*.pack")]
    earlier = [pack_dir / "tmp_pack_earlier", pack_dir / "pack-earlier.keep"]
    for path in earlier:
        path.write_text("x")
    real_path = os.environ["PATH"]
    _shim(
        tmp_path,
        monkeypatch,
        "git",
        f": > '{pack_dir}/tmp_pack_Ab12'\n: > '{pack_dir}/tmp_idx_Ab12'\n"
        f": > '{pack_dir}/pack-0123abcd.keep'\n: > '{pack_dir}/{complete}.keep'\n"
        "echo 'fatal: write error: No space left on device' >&2\nexit 128",
    )

    with pytest.raises(GitCliError) as info:
        await _fetch(clone, _source(git_origin.url))
    left = sorted(
        p.name
        for p in pack_dir.iterdir()
        if p.name.startswith("tmp_") or p.name.endswith(".keep")
    )
    monkeypatch.setenv("PATH", real_path)
    head = git_origin.commit("master")
    await _fetch(clone, _source(git_origin.url))

    assert info.value.returncode == 128
    assert "No space left on device" in info.value.stderr_tail
    assert left == sorted(["pack-earlier.keep", f"{complete}.keep", "tmp_pack_earlier"])
    assert _refs(clone)["refs/remotes/origin/master"] == head


@pytest.fixture
def http_clone(git_http, make_origin, tmp_path):
    """A clone by libgit2 of an origin served over HTTP, fetched once by
    libgit2 (so its FETCH_HEAD has content) and dated long ago."""
    origin = make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git")
    clone = tmp_path / "cli"
    pygit2.clone_repository(url, str(clone)).free()
    origin.commit("master")
    repo = pygit2.Repository(str(clone))
    try:
        repo.remotes["origin"].fetch()
    finally:
        repo.free()
    fetch_head = clone / ".git" / "FETCH_HEAD"
    os.utime(fetch_head, (1_000_000, 1_000_000))
    return origin, url, clone, fetch_head


@pytest.mark.asyncio
async def test_a_fetch_stopped_mid_pack_leaves_fetch_head_as_it_was(
    http_clone, git_http
):
    """Git empties FETCH_HEAD as it starts; a fetch that is stopped must not
    look like one that succeeded to whatever reads FETCH_HEAD's age."""
    origin, url, clone, fetch_head = http_clone
    before = fetch_head.read_text()
    origin.commit("master", {"big.bin": os.urandom(2 * 1024 * 1024)})
    git_http.stall_after = 1024

    with pytest.raises(GitCliTimeoutError):
        await _fetch(clone, _source(url), timeout=3.0)

    assert git_http.stalled.is_set()
    assert fetch_head.stat().st_mtime == 1_000_000
    assert fetch_head.read_text() == before


@pytest.mark.asyncio
async def test_a_failed_fetch_leaves_fetch_head_as_it_was(http_clone, tmp_path):
    origin, url, clone, fetch_head = http_clone
    before = fetch_head.read_text()
    shutil.move(str(origin.path), str(tmp_path / "moved.git"))

    with pytest.raises(GitCliError):
        await _fetch(clone, _source(url))

    assert fetch_head.stat().st_mtime == 1_000_000
    assert fetch_head.read_text() == before


@pytest.mark.asyncio
async def test_a_hung_fetch_that_is_cancelled_leaves_fetch_head_as_it_was(
    http_clone, git_http
):
    origin, url, clone, fetch_head = http_clone
    before = fetch_head.read_text()
    origin.commit("master", {"big.bin": os.urandom(2 * 1024 * 1024)})
    git_http.stall_after = 1024
    task = asyncio.ensure_future(_fetch(clone, _source(url)))
    await asyncio.get_running_loop().run_in_executor(None, git_http.stalled.wait, 10)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert fetch_head.stat().st_mtime == 1_000_000
    assert fetch_head.read_text() == before


def test_libgit2_control_a_failed_fetch_leaves_fetch_head_as_it_was(
    http_clone, tmp_path
):
    """What the git fetch matches: libgit2 writes FETCH_HEAD only once a
    fetch has succeeded."""
    origin, url, clone, fetch_head = http_clone
    before = fetch_head.read_text()
    assert before
    shutil.move(str(origin.path), str(tmp_path / "moved.git"))

    repo = pygit2.Repository(str(clone))
    try:
        with pytest.raises(pygit2.GitError):
            repo.remotes["origin"].fetch()
    finally:
        repo.free()

    assert fetch_head.stat().st_mtime == 1_000_000
    assert fetch_head.read_text() == before


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
@pytest.mark.asyncio
async def test_a_timeout_of_zero_or_less_or_not_finite_means_no_limit(
    timeout, git_origin, tmp_path
):
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone, timeout=timeout)
    new = git_origin.commit("master")

    await _fetch(clone, _source(git_origin.url), timeout=timeout)

    assert _refs(clone)["refs/remotes/origin/master"] == new


@pytest.mark.asyncio
async def test_a_small_fetch_lands_in_one_new_pack_and_no_loose_objects(
    git_origin, tmp_path
):
    """As with libgit2, which the repack trigger (a pack count) is built
    for."""
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    objects = clone / ".git" / "objects"
    packs = set((objects / "pack").glob("*.pack"))
    git_origin.commit("master")

    await _fetch(clone, _source(git_origin.url))

    loose = [p for p in objects.iterdir() if len(p.name) == 2 and any(p.iterdir())]
    assert loose == []
    assert len(set((objects / "pack").glob("*.pack")) - packs) == 1


@pytest.mark.asyncio
async def test_a_fetch_into_a_clone_with_many_packs_starts_no_gc(git_origin, tmp_path):
    """Past gc.autoPackLimit (50 packs, the default of
    SCOPES_GIT_REPACK_PACK_LIMIT too), a plain git fetch starts ``git
    maintenance run --auto``, whose gc repacks the clone outside OPAL's repack
    and its lock.

    Here the fetch adds its one pack, and the clone's 55 others stay.
    The clone's config has gc run in the foreground, so that a gc would
    be over by the time the fetch returns.
    """
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    pack_dir = clone / ".git" / "objects" / "pack"
    repo = pygit2.Repository(str(clone))
    try:
        repo.config["gc.autoDetach"] = False
        repo.config["maintenance.autoDetach"] = False
        blobs = [str(repo.create_blob(f"blob {i}\n")) for i in range(55)]
    finally:
        repo.free()
    for blob in blobs:
        subprocess.run(
            ["git", "-C", str(clone), "pack-objects", "-q", str(pack_dir / "pack")],
            input=f"{blob}\n",
            text=True,
            check=True,
            capture_output=True,
        )
    packs = set(pack_dir.glob("*.pack"))
    assert len(packs) > 55
    git_origin.commit("master")

    await _fetch(clone, _source(git_origin.url))

    after = set(pack_dir.glob("*.pack"))
    assert packs <= after and len(after - packs) == 1


@pytest.mark.asyncio
async def test_a_fetch_uses_the_refspecs_in_the_clone_s_config(git_origin, tmp_path):
    """Git is given the remote's URL instead of its name, so the refspecs it
    fetches come from the clone's config, as libgit2 reads them."""
    cli = tmp_path / "cli"
    await _clone(git_origin.url, cli)
    repo = pygit2.Repository(str(cli))
    try:
        repo.config["remote.origin.fetch"] = "+refs/heads/dev:refs/remotes/origin/dev"
    finally:
        repo.free()
    master = str(git_origin.repo.references["refs/heads/master"].target)
    git_origin.commit("master")
    dev = git_origin.commit("dev")

    await _fetch(cli, _source(git_origin.url))

    assert _refs(cli)["refs/remotes/origin/dev"] == dev
    assert _refs(cli)["refs/remotes/origin/master"] == master


@pytest.mark.asyncio
async def test_prune_off_keeps_a_deleted_branch_even_with_fetch_prune_in_the_clone_s_config(
    git_origin, tmp_path
):
    """The clone's own config is read, as libgit2 reads it, but prune is the
    setting's alone."""
    cli = tmp_path / "cli"
    await _clone(git_origin.url, cli)
    repo = pygit2.Repository(str(cli))
    try:
        repo.config["fetch.prune"] = True
        repo.config["remote.origin.prune"] = True
    finally:
        repo.free()
    git_origin.delete("dev")

    await _fetch(cli, _source(git_origin.url))

    assert "refs/remotes/origin/dev" in _refs(cli)


@pytest.mark.parametrize("remote", ["", "-x", "a b", "--upload-pack=x"])
@pytest.mark.asyncio
async def test_remote_names_git_cannot_take_are_refused(remote, git_origin, tmp_path):
    with pytest.raises(ValueError):
        await cli_fetch(
            tmp_path, remote, _source(git_origin.url), prune=False, timeout=1
        )
    with pytest.raises(ValueError):
        await cli_clone(
            git_origin.url,
            tmp_path / "x",
            _source(git_origin.url),
            remote=remote,
            timeout=1,
        )


@pytest.mark.parametrize(
    "what", ["no such remote", "not a repository", "no such directory"]
)
@pytest.mark.asyncio
async def test_a_fetch_of_a_clone_git_cannot_be_pointed_at_is_a_local_error(
    what, git_origin, tmp_path
):
    cli = tmp_path / "cli"
    await _clone(git_origin.url, cli)
    remote = "origin"
    if what == "no such remote":
        remote = "upstream"
    elif what == "not a repository":
        shutil.rmtree(cli / ".git")
    else:
        cli = tmp_path / "missing"
    gone = _Gone()

    with pytest.raises(GitCliLocalError) as info:
        await cli_fetch(
            cli, remote, _source(git_origin.url), prune=False, timeout=5, on_gone=gone
        )

    assert info.value.returncode == 128
    await gone.wait()
    assert gone.calls == [False]


@pytest.mark.asyncio
async def test_a_git_failure_is_a_git_cli_error_with_git_s_message(tmp_path):
    """Git's message, and nothing of the sh it ran under, which writes "Killed"
    for a job it killed and then waits for."""
    missing = f"file://{tmp_path / 'no-such-repo.git'}"
    gone = _Gone()
    with pytest.raises(GitCliError) as info:
        await _clone(missing, tmp_path / "cli", on_gone=gone)
    assert not isinstance(info.value, GitCliLocalError)
    assert info.value.returncode == 128
    assert "no-such-repo.git" in info.value.stderr_tail
    assert info.value.stderr_tail.endswith("and the repository exists.")
    assert [p.name for p in tmp_path.iterdir()] == [".cli.lock"]
    await gone.wait()
    assert gone.calls == [False]


@pytest.mark.asyncio
async def test_a_clone_into_a_directory_that_is_not_empty_is_refused(
    git_origin, tmp_path
):
    dest = tmp_path / "cli"
    dest.mkdir()
    (dest / "file").write_text("x")
    with pytest.raises(GitCliLocalError) as info:
        await _clone(git_origin.url, dest)
    assert info.value.returncode == 128
    assert sorted(p.name for p in dest.iterdir()) == ["file"]


@pytest.mark.parametrize("step", ["set_url", "rename"])
@pytest.mark.asyncio
async def test_a_clone_that_cannot_be_put_in_place_is_a_local_error_and_leaves_nothing(
    step, git_origin, tmp_path, monkeypatch
):
    def _fail(*args, **kwargs):
        raise OSError(28, "No space left on device")

    if step == "rename":
        monkeypatch.setattr(git_cli.os, "rename", _fail)
    else:
        monkeypatch.setattr(pygit2.remotes.RemoteCollection, "set_url", _fail)
    dest = tmp_path / "clones" / "cli"
    gone = _Gone()

    with pytest.raises(GitCliLocalError, match="could not put the clone in place"):
        await _clone(git_origin.url, dest, on_gone=gone)

    assert [p.name for p in dest.parent.iterdir()] == [".cli.lock"]
    await gone.wait()
    assert gone.calls == [False]


@pytest.mark.parametrize(
    "what",
    ["unreadable known_hosts", "key file", "newline", "no git", "no pipe", "no sh"],
)
@pytest.mark.asyncio
async def test_a_clone_that_never_runs_git_leaves_no_directory_behind(
    what, git_origin, tmp_path, monkeypatch
):
    """Whatever keeps git from running once the directory the clone goes in
    is made: SSH settings or a key file that cannot be used, a credential git
    cannot be given, no git, no pipe for sh's watchdog, no sh."""
    url = git_origin.url
    source = _source(url)
    if what == "unreadable known_hosts":
        url = "ssh://git@127.0.0.1:1/repo.git"
        source = _source(url)
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
        monkeypatch.setattr(
            opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(tmp_path / "gone")
        )
    elif what == "key file":
        source = _source(url, SSHAuthData(username="git", private_key=_FAKE_KEY))

        def _no_key(key_dir, private_key):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(git_cli, "_write_key", _no_key)
    elif what == "newline":
        url = "http://alice:a%0Ab@127.0.0.1:1/repo.git"
        source = _source(url)
    elif what == "no git":
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    elif what == "no pipe":
        real_pipe = os.pipe
        calls = []

        def _no_pipe():
            calls.append(True)
            if len(calls) == 1:
                raise OSError(24, "Too many open files")
            return real_pipe()

        monkeypatch.setattr(git_cli.os, "pipe", _no_pipe)
    else:
        monkeypatch.setattr(git_cli, "_SH", str(tmp_path / "no-sh"))
    dest = tmp_path / "clones" / "cli"
    gone = _Gone()

    with pytest.raises(GitCliLocalError):
        await _clone(url, dest, source, on_gone=gone)
    await gone.wait()

    assert gone.calls == [False]
    assert [p.name for p in dest.parent.iterdir()] == [".cli.lock"]
    assert clone_lock_path(dest).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_clone_whose_parent_cannot_be_made_is_a_local_error(
    git_origin, tmp_path
):
    (tmp_path / "file").write_text("x")
    with pytest.raises(GitCliLocalError):
        await _clone(git_origin.url, tmp_path / "file" / "cli")


@pytest.mark.parametrize(
    "url_format, message",
    [
        ("alice:pw@127.0.0.1:{marker}.git", "scp-like URL with a password"),
        ("http://127.0.0.1:99999/{marker}.git", "does not parse"),
        ("http://[::1/{marker}.git", "does not parse"),
        ("https://127.0.0.1/{marker}.git?private_token=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?x=1&Access_Token=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?token=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?password=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?api_key=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?apikey=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?key=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?secret=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?sig=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?signature=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?x=1;key=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?%74oken=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git#token=abc", "token auth"),
        ("https://127.0.0.1/{marker}.git?x=1#y=2&Password=abc", "token auth"),
        ("ssh://pw:pw@127.0.0.1/{marker}.git", "cannot be taken out"),
    ],
    ids=[
        "scp-password",
        "bad-port",
        "bad-host",
        "private_token",
        "access_token",
        "token",
        "password",
        "api_key",
        "apikey",
        "key",
        "secret",
        "sig",
        "signature",
        "after-a-semicolon",
        "encoded-name",
        "fragment",
        "fragment-after-a-query",
        "ssh-user-is-the-password",
    ],
)
@pytest.mark.asyncio
async def test_a_url_git_cannot_be_given_without_a_credential_on_its_command_line_is_refused(
    url_format, message, git_origin, tmp_path, processes_with
):
    """Before anything runs: git would put the URL on its remote helper's
    command line, and print it in its errors.

    A credential in the query string or the fragment is any parameter
    OPAL's redaction counts as one (and GitLab's private_token).
    """
    marker = f"refused-{uuid.uuid4().hex}"
    url = url_format.format(marker=marker)
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    _point_at(clone, url)
    for run in (
        lambda: _clone(url, tmp_path / "new"),
        lambda: _fetch(clone, _source(git_origin.url)),
    ):
        task, seen, _ = await _run_and_watch(run(), marker, processes_with)
        error = task.exception()
        assert isinstance(error, GitCliLocalError), error
        assert message in str(error)
        assert "abc" not in str(error) and "pw" not in str(error)
        assert seen == set()


@pytest.mark.parametrize(
    "query", ["?ref=main", "?keys=1&tokens=2", "?token=", "#key"], ids=str
)
def test_a_url_whose_query_or_fragment_holds_no_credential_is_not_refused(query):
    """A parameter of another name, or one of those names with no value, is
    no credential: the URL is given to git as it is."""
    url = f"https://127.0.0.1/repo.git{query}"

    assert git_cli._remote_for_git(url, _source(url)).url == url


def test_credentials_are_left_out_of_the_remote_s_repr():
    remote = git_cli._remote_for_git(
        "https://alice:s3cret@127.0.0.1/repo.git",
        _source("https://127.0.0.1/repo.git", GitHubTokenAuthData(token="t0ken")),
    )
    assert remote.credential is not None
    assert "s3cret" not in repr(remote) and "t0ken" not in repr(remote)


def test_the_remote_s_repr_names_only_the_url():
    """The repr goes into logs and tracebacks, so it names the URL git is
    given and nothing else: not a user that is a secret as a word of its own,
    nor the text kept from redaction."""
    remote = git_cli._remote_for_git(
        "https://ci@127.0.0.1:8443/repo.git", _source("https://127.0.0.1:8443/repo.git")
    )
    assert remote.word_secrets and remote.kept
    assert repr(remote) == f"_Remote(url={remote.url!r})"


@pytest.mark.asyncio
async def test_a_clone_into_an_empty_directory_takes_its_place(git_origin, tmp_path):
    dest = tmp_path / "cli"
    dest.mkdir()
    await _clone(git_origin.url, dest)
    assert "refs/remotes/origin/master" in _refs(dest)


@pytest.mark.asyncio
async def test_no_git_on_path_is_a_local_error(git_origin, tmp_path, monkeypatch):
    cli = tmp_path / "cli"
    await _clone(git_origin.url, cli)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    gone = _Gone()
    with pytest.raises(GitCliLocalError) as info:
        await _fetch(cli, _source(git_origin.url), timeout=5, on_gone=gone)
    assert info.value.returncode == 127
    await gone.wait()
    assert gone.calls == [False]
    assert clone_lock_path(cli).read_bytes() == b""


@pytest.mark.parametrize("what", ["sh", "the SSH key directory"])
@pytest.mark.asyncio
async def test_what_cannot_be_started_or_set_up_is_a_local_error(
    what, git_origin, tmp_path, monkeypatch
):
    cli = tmp_path / "cli"
    await _clone(git_origin.url, cli)
    source = _source(git_origin.url)
    if what == "sh":
        monkeypatch.setattr(git_cli, "_SH", str(tmp_path / "no-sh"))
        returncode = 127
    else:
        source = _source(
            git_origin.url, SSHAuthData(username="git", private_key=_FAKE_KEY)
        )
        monkeypatch.setattr(git_cli, "_key_dir_parent", lambda: str(tmp_path / "none"))
        returncode = 128
    gone = _Gone()

    with pytest.raises(GitCliLocalError) as info:
        await _fetch(cli, source, on_gone=gone)

    assert info.value.returncode == returncode
    await gone.wait()
    assert gone.calls == [False]
    assert clone_lock_path(cli).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_git_whose_sh_was_killed_is_never_a_success(
    git_origin, tmp_path, monkeypatch
):
    """git exits 0, but the sh it runs under is killed before it can report
    that: with no status there is no telling what git did, so it is a
    failure, whatever the reaped sh's own status reads, and what a git
    killed in the middle could have left in the clone is removed."""
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    stale = clone / ".git" / "packed-refs.lock"
    stale.write_text("x")
    _shim(tmp_path, monkeypatch, "git", "kill -9 $PPID\nexit 0")
    gone = _Gone()

    with pytest.raises(GitCliError) as info:
        await _fetch(clone, _source(git_origin.url), on_gone=gone)

    assert info.value.returncode == -1
    assert "before it reported git's exit status" in info.value.stderr_tail
    assert not stale.exists()
    await gone.wait()
    assert gone.calls == [False]


@pytest.mark.parametrize(
    "dies, status",
    [
        ("kill -KILL $$", 137),
        ("kill -TERM $$", 143),
        ("kill -SEGV $$", 139),
        ("exit 128", 128),
        ("exit 255", 255),
    ],
    ids=["sigkill", "sigterm", "sigsegv", "fatal", "fatal-255"],
)
@pytest.mark.asyncio
async def test_what_a_git_killed_by_a_signal_opal_did_not_send_left_is_removed(
    dies, status, git_origin, tmp_path, monkeypatch
):
    """An OOM kill (status 137) or a crash leaves the locks git held, and the
    packed-refs.new it was writing under packed-refs.lock, which would fail
    every later fetch of the clone that has to write them.

    A git that exited by itself, with 255 as some of its fatal errors do
    included, removed its own, and the locks it found held may be live:
    they stay. The temp files of a pack go either way.
    """
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    lock = clone / ".git" / "refs" / "remotes" / "origin" / "master.lock"
    tmp_pack = clone / ".git" / "objects" / "pack" / "tmp_pack_Ab12"
    new_packed_refs = clone / ".git" / "packed-refs.new"
    _shim(
        tmp_path,
        monkeypatch,
        "git",
        f": > '{lock}'\n: > '{tmp_pack}'\n: > '{new_packed_refs}'\n{dies}",
    )

    with pytest.raises(GitCliError) as info:
        await _fetch(clone, _source(git_origin.url))

    assert info.value.returncode == status
    removed = status in (137, 139, 143)
    assert lock.exists() is not removed
    assert new_packed_refs.exists() is not removed
    assert not tmp_pack.exists()


def test_a_death_by_signal_is_sh_s_128_plus_a_signal_number_or_no_status():
    killed = [None, -9, 129, 137, 143, 192]
    exited = [0, 1, 128, 193, 255]
    assert [git_cli.killed_by_signal(s) for s in killed] == [True] * len(killed)
    assert [git_cli.killed_by_signal(s) for s in exited] == [False] * len(exited)


@pytest.mark.asyncio
async def test_a_pruning_fetch_after_a_git_killed_mid_packed_refs_deletes_the_branch(
    git_origin, tmp_path
):
    """A git SIGKILLed while it rewrote packed-refs (as a clone git made has
    it) leaves packed-refs.new beside packed-refs.lock; git creates that file
    O_EXCL, so every later rewrite of packed-refs fails on it, the ref
    deletions of a pruning fetch included, and a branch deleted on the remote
    would be served on.

    The next op on the clone removes both, and its pruning fetch deletes
    the branch.
    """
    git_origin.branch("gone")
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    git_dir = clone / ".git"
    assert "refs/remotes/origin/gone" in (git_dir / "packed-refs").read_text()
    (git_dir / "packed-refs.lock").write_text("")
    (git_dir / "packed-refs.new").write_text("")
    clone_lock_path(clone).write_text("4194303\n")  # an op whose process died
    git_origin.delete("gone")

    await _fetch(clone, _source(git_origin.url), prune=True)

    assert "refs/remotes/origin/gone" not in _refs(clone)
    assert "refs/remotes/origin/master" in _refs(clone)
    assert not (git_dir / "packed-refs.new").exists()
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_dead_op_s_record_stays_until_all_it_left_is_removed(
    git_origin, tmp_path
):
    """What an op whose process died left that cannot be removed (here a
    directory where packed-refs.new would be, which unlink cannot remove) keeps
    that op recorded in the clone's lock file, so the next op tries again; once
    it is all gone, the record goes."""
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    stuck = clone / ".git" / "packed-refs.new"
    (stuck / "x").mkdir(parents=True)
    clone_lock_path(clone).write_text("4194303\n")

    await _fetch(clone, _source(git_origin.url))
    kept = clone_lock_path(clone).read_bytes()
    shutil.rmtree(stuck)
    await _fetch(clone, _source(git_origin.url))

    assert kept != b""
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.asyncio
async def test_an_op_that_cannot_record_itself_keeps_a_dead_op_s_record(
    git_origin, tmp_path, monkeypatch
):
    """The lock file holds a dead op's record, and the next op cannot write its
    own (a full disk: ENOSPC).

    That op fails without running git, and the dead op stays recorded,
    so the op after it still removes what it left (here a stale packed-
    refs.lock).
    """
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    stale = clone / ".git" / "packed-refs.lock"
    stale.write_text("")
    clone_lock_path(clone).write_text("4194303\n")

    def _full(fd, data, offset):
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    with monkeypatch.context() as full_disk:
        full_disk.setattr(git_cli.os, "pwrite", _full)
        with pytest.raises(GitCliLocalError, match="cannot record the op"):
            await _fetch(clone, _source(git_origin.url))
    kept = clone_lock_path(clone).read_bytes()
    await _fetch(clone, _source(git_origin.url))

    assert kept != b""
    assert not stale.exists()
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_dead_op_s_clone_that_cannot_be_looked_at_keeps_its_record(
    git_origin, tmp_path
):
    """The next op on a clone whose git dir cannot be looked at (EACCES here,
    EIO on a failing disk) cannot remove what a dead op left there: it fails as
    a local error, and the clone stays recorded as having an op that never
    finished, for an op after it to try again."""
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    clone_lock_path(clone).write_text("4194303\n")
    clone.chmod(0o600)
    try:
        if os.access(clone, os.X_OK):
            pytest.skip("this user reads every directory (root)")
        assert git_cli.remove_dead_op_leftovers(clone) is False
        with pytest.raises(GitCliLocalError):
            await _clone(git_origin.url, clone)
    finally:
        clone.chmod(0o700)

    assert clone_lock_path(clone).read_bytes() != b""
    assert git_cli._lock_fds == {}


@pytest.mark.asyncio
async def test_a_dead_op_s_git_dir_that_fails_to_stat_keeps_what_the_op_left(
    git_origin, tmp_path, monkeypatch
):
    """The same with EIO, injected rather than made with permissions, so that
    it runs as root too: the clean-up removes nothing in a git dir it cannot
    look at, and says not all of it is gone, so the dead op stays recorded.
    Once the git dir can be looked at, the next clean-up removes it."""
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    leftover = clone / ".git" / "packed-refs.lock"
    leftover.write_text("")
    git_dir = os.fspath(clone / ".git")
    real_stat = os.stat

    def _stat(path, *args, **kwargs):
        if os.fspath(path) == git_dir:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        return real_stat(path, *args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(git_cli.os, "stat", _stat)
        assert git_cli.remove_dead_op_leftovers(clone) is False
    assert leftover.exists()

    assert git_cli.remove_dead_op_leftovers(clone) is True
    assert not leftover.exists()


def test_a_clone_path_that_is_a_file_has_nothing_of_a_dead_op_to_remove(tmp_path):
    """A file where a clone would be (a name in the clones directory that could
    be a source id's) has no git dir: as for a clone that is not there, nothing
    a dead op left is in it, and all of it counts as gone."""
    stray = tmp_path / "stray"
    stray.write_text("not a clone")

    assert git_cli.remove_dead_op_leftovers(stray) is True
    assert stray.read_text() == "not a clone"


@pytest.mark.asyncio
async def test_an_op_that_cannot_clear_its_record_still_succeeds(
    git_origin, tmp_path, monkeypatch
):
    """An op that cannot clear its own record from the lock file as it ends
    (the ftruncate fails) still succeeds, and says so.

    It stays recorded, so the next op on the clone cleans up once more
    before it runs, and clears it.
    """
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    truncate = os.ftruncate

    def _cannot_clear(fd, length):
        if length == 0:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        truncate(fd, length)

    warnings = []
    sink = logger.add(lambda m: warnings.append(m.record["message"]), level="WARNING")
    gone = _Gone()
    try:
        with monkeypatch.context() as patched:
            patched.setattr(git_cli.os, "ftruncate", _cannot_clear)
            await _fetch(clone, _source(git_origin.url), on_gone=gone)
    finally:
        logger.remove(sink)
    kept = clone_lock_path(clone).read_bytes()
    await _fetch(clone, _source(git_origin.url))

    assert gone.calls == [True]
    assert kept == f"{os.getpid()}\n".encode()
    assert [m for m in warnings if "Could not clear a finished git op" in m]
    assert git_cli._lock_fds == {}
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_killed_git_s_leftover_that_cannot_be_removed_keeps_its_op_recorded(
    git_origin, tmp_path, monkeypatch
):
    """The same for what a git killed by a signal left: the op stays recorded,
    and the next op on the clone tries again."""
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    stuck = clone / ".git" / "packed-refs.new"
    _shim(tmp_path, monkeypatch, "git", f"mkdir -p '{stuck}/x'\nkill -KILL $$")

    with pytest.raises(GitCliError):
        await _fetch(clone, _source(git_origin.url))

    assert stuck.exists()
    assert clone_lock_path(clone).read_bytes() != b""


@pytest.mark.parametrize("unfinished", [True, False], ids=["dead-op", "none"])
@pytest.mark.asyncio
async def test_a_fetch_after_a_dead_op_removes_the_directories_its_clones_left(
    unfinished, git_origin, tmp_path
):
    """A clone whose process died leaves the directory it was cloning into; the
    next op on the path removes it whatever that op is, a fetch included (a
    clone of the path made since, by libgit2 say, comes first).

    With no op unfinished, a directory named like one is not one, and
    stays.
    """
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    left = tmp_path / ".cli.clone-0000000000000000"
    (left / ".git").mkdir(parents=True)
    if unfinished:
        clone_lock_path(clone).write_text("4194303\n")

    await _fetch(clone, _source(git_origin.url))

    assert left.exists() is not unfinished
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_clone_after_one_whose_process_died_removes_the_directories_it_left(
    git_origin, tmp_path
):
    """A clone whose process died leaves the directory it was cloning into, and
    its pid in the clone's lock file.

    The next clone of that path, under the lock, removes every such
    directory of that path, however young, and no other path's.
    """
    dest = tmp_path / "clones" / "source"
    dest.parent.mkdir()
    left = [dest.parent / f".source.clone-{n}" for n in ("0" * 16, "1" * 16)]
    other = dest.parent / ".other.clone-2222222222222222"
    for d in (*left, other):
        (d / ".git").mkdir(parents=True)
    clone_lock_path(dest).write_text("4194303\n")

    await _clone(git_origin.url, dest)

    assert [d for d in left if d.exists()] == []
    assert other.exists()
    assert clone_lock_path(dest).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_clone_after_ops_that_all_finished_leaves_other_directories_alone(
    git_origin, tmp_path
):
    """No op of that path is unfinished, so a directory named like one of its
    clones is not one: left for the pre-fork sweep, which runs before any
    op."""
    dest = tmp_path / "clones" / "source"
    dest.parent.mkdir()
    odd = dest.parent / ".source.clone-3333333333333333"
    odd.mkdir()

    await _clone(git_origin.url, dest)

    assert odd.exists()


def test_kill_grace_is_validated(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    for value, expected in ((2.5, 2.5), (0, 0.0)):
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", value)
        assert kill_grace_seconds() == expected
        validate_git_cli_settings()
    for value in (-1, float("nan"), float("inf"), "soon"):
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", value)
        assert kill_grace_seconds() == 5.0
        with pytest.raises(ValueError, match="SCOPES_GIT_CLI_KILL_GRACE"):
            validate_git_cli_settings()


# --- stopping an op that hangs ---------------------------------------------------


@pytest.fixture
def hung_clone(git_origin, tmp_path):
    """A clone (by libgit2, as most clones the CLI fetches will be) and a
    function that points its origin at a URL with a unique marker in its path,
    to find the op's processes by."""
    clone = tmp_path / "cli"
    pygit2.clone_repository(git_origin.url, str(clone)).free()

    def _point(url_format: str) -> tuple:
        marker = f"hung-{uuid.uuid4().hex}"
        url = url_format.format(marker=marker)
        _point_at(clone, url)
        return url, marker

    return clone, _point


@pytest.mark.parametrize(
    "url_format, member",
    [
        ("http://127.0.0.1:{port}/{{marker}}.git", "remote-http"),
        ("ssh://git@127.0.0.1:{port}/{{marker}}.git", "ssh "),
    ],
    ids=["http", "ssh"],
)
@pytest.mark.asyncio
async def test_a_fetch_from_a_blackholed_remote_ends_at_its_timeout_with_no_process_left(
    url_format, member, hung_clone, blackhole, processes_with
):
    """The remote takes the connection and never answers.

    libgit2 would wait
    for it for good; git is stopped at the timeout, and every process of
    the op is gone when the call returns: git, its remote helper, ssh.
    By then on_gone has been called, and the clone's lock is free.
    """
    clone, point = hung_clone
    url, marker = point(url_format.format(port=blackhole))
    gone = _Gone()

    task, seen, elapsed = await _run_and_watch(
        _fetch(clone, _source(url), timeout=_HUNG_TIMEOUT, on_gone=gone),
        marker,
        processes_with,
    )

    error = task.exception()
    assert isinstance(error, GitCliTimeoutError), error
    assert isinstance(error, TimeoutError)
    await gone.wait()
    assert gone.calls == [False]
    assert _HUNG_TIMEOUT <= elapsed <= _HUNG_TIMEOUT + _GRACE + 3
    assert any(member in args for _, _, args in seen), seen
    assert processes_with(marker) == []
    assert _leftovers(clone) == []
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.asyncio
async def test_a_fetch_whose_answer_drips_in_forever_is_stopped_at_its_timeout(
    hung_clone, dripper, processes_with
):
    """A remote that keeps sending, slowly: the transfer never stalls, so no
    read timeout (libgit2's server timeout included) would ever end it."""
    clone, point = hung_clone
    url, marker = point(f"http://127.0.0.1:{dripper.port}/{{marker}}.git")

    task, seen, elapsed = await _run_and_watch(
        _fetch(clone, _source(url), timeout=_HUNG_TIMEOUT), marker, processes_with
    )

    assert isinstance(task.exception(), GitCliTimeoutError)
    assert _HUNG_TIMEOUT <= elapsed <= _HUNG_TIMEOUT + _GRACE + 3
    assert dripper.bytes_sent > 0
    assert seen
    assert processes_with(marker) == []


@pytest.mark.asyncio
async def test_a_git_that_ends_on_sigterm_is_not_kept_for_the_kill_grace(
    hung_clone, blackhole, monkeypatch, processes_with
):
    """The stop's SIGTERM reaches every member of the group, git's remote
    helper included, not sh alone (which outlives it, to report git's status).

    A git that ends on it ends the op then, long before the grace is
    over.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 30.0)
    clone, point = hung_clone
    url, marker = point(f"http://127.0.0.1:{blackhole}/{{marker}}.git")

    task, seen, elapsed = await _run_and_watch(
        _fetch(clone, _source(url), timeout=_HUNG_TIMEOUT), marker, processes_with
    )

    assert isinstance(task.exception(), GitCliTimeoutError)
    assert seen
    assert _HUNG_TIMEOUT <= elapsed <= _HUNG_TIMEOUT + 3
    assert processes_with(marker) == []


@pytest.mark.parametrize(
    "stderr", ["kept open", "closed early"], ids=["stderr-open", "stderr-closed"]
)
@pytest.mark.asyncio
async def test_a_member_that_ignores_sigterm_is_killed_whatever_it_does_with_stderr(
    stderr, hung_clone, tmp_path, monkeypatch, processes_with
):
    """An ssh that ignores SIGTERM outlives the SIGTERM git gets.

    Whether it keeps the op's stderr open or closed it early, the group
    is not taken for gone while it runs: it gets SIGKILL after the grace,
    and the op returns once it is dead.
    """
    closing = "exec 2>&-\n" if stderr == "closed early" else ""
    started = _shim(
        tmp_path,
        monkeypatch,
        "ssh",
        f'{closing}exec "{sys.executable}" -c '
        '"import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
        'time.sleep(30)" "$@"',
    )
    clone, point = hung_clone
    url, marker = point("ssh://git@127.0.0.1:1/{marker}.git")
    gone = _Gone()

    task, seen, elapsed = await _run_and_watch(
        _fetch(clone, _source(url), timeout=_SHIM_TIMEOUT, on_gone=gone),
        marker,
        processes_with,
    )

    assert started.exists(), "git was stopped before it started ssh"
    assert isinstance(task.exception(), GitCliTimeoutError)
    await gone.wait()
    assert gone.calls == [False]
    assert any(sys.executable in args for _, _, args in seen), seen
    # SIGKILL at the grace's end, long before the member's own 30 s were up.
    assert _SHIM_TIMEOUT + _GRACE <= elapsed <= _SHIM_TIMEOUT + _GRACE + 10
    assert processes_with(marker) == []


@pytest.mark.parametrize("grace", [0.0, 1.0], ids=["sigkill", "sigterm"])
@pytest.mark.asyncio
async def test_a_fetch_stopped_mid_pack_leaves_a_clone_the_next_fetch_and_fsck_accept(
    grace, git_http, make_origin, tmp_path, monkeypatch
):
    """Stopped while the pack comes in, git leaves its partial pack
    (objects/pack/tmp_pack_*) and, under SIGKILL, any lock it held.

    Every one of them is gone once the op returns, the next fetch
    succeeds, and fsck finds nothing wrong.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", grace)
    origin = make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git")
    clone = tmp_path / "cli"
    await _clone(url, clone)
    big = origin.commit("master", {"big.bin": os.urandom(4 * 1024 * 1024)})
    git_http.stall_after = 256 * 1024
    pack_dir = clone / ".git" / "objects" / "pack"
    partial = set()

    async def _watch_pack():
        while True:
            for path in pack_dir.glob("tmp_*"):
                try:
                    if path.stat().st_size > 0:
                        partial.add(path.name)
                except FileNotFoundError:
                    pass
            await asyncio.sleep(0.02)

    watcher = asyncio.ensure_future(_watch_pack())
    try:
        with pytest.raises(GitCliTimeoutError):
            await _fetch(clone, _source(url), timeout=3.0)
    finally:
        watcher.cancel()

    assert git_http.stalled.is_set()
    assert partial, "the fetch was not stopped in the middle of a pack"
    assert _leftovers(clone) == []
    git_http.stall_after = None
    await _fetch(clone, _source(url))
    assert _refs(clone)["refs/remotes/origin/master"] == big
    fsck = _fsck(clone)
    assert fsck.returncode == 0, fsck.stdout + fsck.stderr


@pytest.mark.asyncio
async def test_what_a_killed_fetch_left_is_removed_once_its_group_is_gone(
    hung_clone, blackhole
):
    """The lock files git takes while it updates refs, its partial pack, and
    the .keep index-pack writes for a fetch, whatever pid and host it names:
    under the clone's lock, no fetch that wrote one is alive.

    A .keep that is not a fetch's stays.
    """
    clone, point = hung_clone
    url, _ = point(f"http://127.0.0.1:{blackhole}/{{marker}}.git")
    git_dir = clone / ".git"
    pack_dir = git_dir / "objects" / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    left = [
        git_dir / "refs" / "remotes" / "origin" / "master.lock",
        git_dir / "refs" / "remotes" / "origin" / "feature" / "x.lock",
        git_dir / "packed-refs.lock",
        git_dir / "FETCH_HEAD.lock",
        git_dir / "shallow.lock",
        git_dir / "index.lock",
        pack_dir / "tmp_pack_AbCdEf",
        pack_dir / "tmp_idx_AbCdEf",
    ]
    for path in left:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    host = socket.gethostname()
    fetch_keeps = {
        pack_dir / "pack-1111.keep": f"fetch-pack {_dead_pid()} on {host}\n",
        pack_dir / "pack-2222.keep": f"fetch-pack {os.getpid()} on {host}\n",
        pack_dir / "pack-4444.keep": f"fetch-pack {_dead_pid()} on not-{host}\n",
    }
    for keep, text in fetch_keeps.items():
        keep.write_text(text)
    kept = pack_dir / "pack-3333.keep"
    kept.write_text("keep this one\n")

    with pytest.raises(GitCliTimeoutError):
        await _fetch(clone, _source(url), timeout=_TIMEOUT)

    assert [p for p in left if p.exists()] == []
    assert [k for k in fetch_keeps if k.exists()] == []
    assert kept.exists()


def _dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


@pytest.mark.asyncio
async def test_a_cancelled_fetch_still_stops_git_and_waits_for_it(
    hung_clone, blackhole, processes_with, git_groups
):
    clone, point = hung_clone
    url, marker = point(f"http://127.0.0.1:{blackhole}/{{marker}}.git")
    gone = _Gone()
    task = asyncio.ensure_future(_fetch(clone, _source(url), on_gone=gone))
    deadline = time.monotonic() + 30
    while not (processes_with(marker) and git_groups):
        assert time.monotonic() < deadline, "git never started"
        await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert processes_with(marker) == []
    assert _leftovers(clone) == []
    await gone.wait()
    assert gone.calls == [False]


@pytest.mark.asyncio
async def test_a_timed_out_clone_leaves_nothing_behind(
    tmp_path, blackhole, processes_with
):
    marker = f"hung-{uuid.uuid4().hex}"
    url = f"http://127.0.0.1:{blackhole}/{marker}.git"
    dest = tmp_path / "clones" / "source"

    with pytest.raises(GitCliTimeoutError):
        await _clone(url, dest, timeout=_TIMEOUT)

    assert not dest.exists()
    assert [p.name for p in dest.parent.iterdir()] == [".source.lock"]
    assert processes_with(marker) == []


@pytest.mark.asyncio
async def test_a_cancelled_clone_leaves_nothing_behind(
    tmp_path, blackhole, processes_with, git_groups
):
    marker = f"hung-{uuid.uuid4().hex}"
    url = f"http://127.0.0.1:{blackhole}/{marker}.git"
    dest = tmp_path / "clones" / "source"
    task = asyncio.ensure_future(_clone(url, dest))
    deadline = time.monotonic() + 30
    while not (processes_with(marker) and git_groups):
        assert time.monotonic() < deadline, "git never started"
        await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert processes_with(marker) == []
    assert not dest.exists()
    assert [p.name for p in dest.parent.iterdir()] == [".source.lock"]


@pytest.mark.asyncio
async def test_a_member_that_outlives_sigkill_keeps_the_clone_until_it_exits(
    hung_clone, git_origin, tmp_path, monkeypatch
):
    """A process of the group that SIGKILL cannot stop (in the wild, one in
    uninterruptible I/O; here, one that moved to a session of its own, out of
    the group's reach) may still write to the clone: nothing is removed and
    on_gone is not called until it has exited, and meanwhile it holds the
    clone's lock, so no other op touches the clone.

    It exits once let go.
    """
    out = tmp_path / "out"
    release = tmp_path / "release"
    survivor = (
        "import os, sys, time\n"
        "os.setsid()\n"
        "open(sys.argv[1], 'w').close()\n"
        "deadline = time.monotonic() + 120\n"
        "while not os.path.exists(sys.argv[2]) and time.monotonic() < deadline:\n"
        "    time.sleep(0.05)\n"
    )
    _shim(
        tmp_path,
        monkeypatch,
        "ssh",
        f"exec \"{sys.executable}\" -c \"{survivor}\" '{out}' '{release}'",
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 0.3)
    clone, point = hung_clone
    url, _ = point("ssh://git@127.0.0.1:1/{marker}.git")
    stale = clone / ".git" / "packed-refs.lock"
    stale.write_text("x")
    gone = _Gone()

    try:
        with pytest.raises(GitCliTimeoutError):
            await _fetch(clone, _source(url), timeout=_SHIM_TIMEOUT, on_gone=gone)

        assert out.exists(), "git was stopped before its ssh left the group"
        assert gone.calls == []
        assert stale.exists()
        with pytest.raises(git_cli.GitCliBusyError):
            await _fetch(clone, _source(git_origin.url))
    finally:
        release.touch()
    await gone.wait()
    assert gone.calls == [False]
    assert not stale.exists()
    assert clone_lock_path(clone).read_bytes() == b""


@pytest.mark.parametrize("where", ["live_members", "kill_grace_seconds"])
@pytest.mark.asyncio
async def test_a_stop_that_fails_still_kills_git_and_finishes_the_op(
    where, hung_clone, blackhole, monkeypatch, processes_with
):
    """Something other than a cancellation goes wrong in a stop: an OSError
    out of the check for the group's members once git has ended on SIGTERM,
    or out of the stop's first step, while git still runs.

    The op is not left waiting for good with its clone's lock held: its
    group gets SIGKILL, the op finishes (on_gone, the lock released) and
    the fetch raises its timeout.
    """

    def _broken(*args) -> bool:
        raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))

    monkeypatch.setattr(git_cli, where, _broken)
    clone, point = hung_clone
    url, marker = point(f"http://127.0.0.1:{blackhole}/{{marker}}.git")
    gone = _Gone()

    with pytest.raises(GitCliTimeoutError):
        await asyncio.wait_for(
            _fetch(clone, _source(url), timeout=_TIMEOUT, on_gone=gone), 15
        )

    await gone.wait()
    assert gone.calls == [False]
    assert clone_lock_path(clone).read_bytes() == b""
    assert await git_cli.wait_for_background_ops(5)
    deadline = time.monotonic() + 10
    while processes_with(marker):
        assert time.monotonic() < deadline, processes_with(marker)
        await asyncio.sleep(0.05)


@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="the filter reads /proc")
def test_a_group_whose_processes_cannot_be_listed_counts_as_having_members(
    monkeypatch,
):
    """An error listing /proc (EMFILE, say) says nothing of the group: its
    members are taken to be there, as without /proc, and the stop goes on to
    SIGKILL rather than fail."""
    live = subprocess.Popen(["sleep", "30"], start_new_session=True)

    def _emfile(path):
        raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))

    try:
        with monkeypatch.context() as patched:
            patched.setattr(git_cli.os, "listdir", _emfile)
            members = git_cli.live_members(live.pid)
    finally:
        live.kill()
        live.wait()

    assert members is True


@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="the filter reads /proc")
@pytest.mark.parametrize(
    "code, members",
    [(errno.EMFILE, True), (errno.ENOENT, False), (errno.EACCES, False)],
    ids=["EMFILE", "gone", "another-user-s"],
)
def test_a_process_that_cannot_be_read_counts_as_a_member_unless_it_is_gone(
    code, members, monkeypatch
):
    """A process whose /proc/<pid>/stat cannot be read for want of an fd
    (EMFILE) may be the group's: as when /proc cannot be listed, the group is
    taken to have members, and the op waits rather than finish under a live
    git.

    One whose stat is not there any more exited meanwhile, and one this
    user may not read (/proc mounted with hidepid=1) is another user's,
    not git's.
    """
    live = subprocess.Popen(["sleep", "30"], start_new_session=True)

    def _open(path, *args, **kwargs):
        if str(path).startswith("/proc/") and str(path).endswith("/stat"):
            raise OSError(code, os.strerror(code))
        return open(path, *args, **kwargs)

    try:
        with monkeypatch.context() as patched:
            patched.setattr(git_cli, "open", _open, raising=False)
            found = git_cli.live_members(live.pid)
    finally:
        live.kill()
        live.wait()

    assert found is members


def test_a_member_listed_after_another_user_s_process_still_counts(monkeypatch):
    """A process this user may not read (another user's, under /proc's
    hidepid=1) says nothing of the group, and the look through /proc goes on
    past it: a live member listed after it is found."""
    pgid = 4242
    stats = {"/proc/100/stat": None, "/proc/200/stat": f"200 (git) S 1 {pgid} 0"}
    real_isdir, real_listdir = os.path.isdir, os.listdir

    def _open(path, *args, **kwargs):
        if stats[str(path)] is None:
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES))
        return io.StringIO(stats[str(path)])

    with monkeypatch.context() as patched:
        patched.setattr(git_cli.os, "killpg", lambda group, signal: None)
        patched.setattr(
            git_cli.os.path, "isdir", lambda p: p == "/proc/self" or real_isdir(p)
        )
        patched.setattr(
            git_cli.os,
            "listdir",
            lambda p: ["self", "100", "200"] if p == "/proc" else real_listdir(p),
        )
        patched.setattr(git_cli, "open", _open, raising=False)
        found = git_cli.live_members(pgid)

    assert found is True


@pytest.fixture
def reaped_elsewhere(monkeypatch):
    """Every child asyncio reaps was already reaped by someone else, as when
    the gunicorn master's SIGCHLD handler gets to it first: asyncio then
    reports 255 for it (with asyncio's pidfd child watching, for every child).

    The pids taken are recorded.
    """
    real_waitpid = os.waitpid
    taken = []

    def _waitpid(pid, options):
        result = real_waitpid(pid, options)
        if pid > 0 and options == 0:
            taken.append(pid)
            raise ChildProcessError(errno.ECHILD, os.strerror(errno.ECHILD))
        return result

    monkeypatch.setattr(os, "waitpid", _waitpid)
    return taken


@pytest.mark.asyncio
async def test_git_s_status_survives_another_reaper_taking_its_process(
    git_origin, tmp_path, reaped_elsewhere
):
    """Git's status comes from sh's stdout, not from waitpid: a fetch that
    succeeded still succeeds, and one that failed reports git's own status."""
    clone = tmp_path / "cli"
    pygit2.clone_repository(git_origin.url, str(clone)).free()
    new = git_origin.commit("master")

    await _fetch(clone, _source(git_origin.url))
    _point_at(clone, f"file://{tmp_path / 'gone.git'}")
    with pytest.raises(GitCliError) as info:
        await _fetch(clone, _source(git_origin.url))

    assert len(reaped_elsewhere) >= 2
    assert _refs(clone)["refs/remotes/origin/master"] == new
    assert info.value.returncode == 128


@pytest.mark.asyncio
async def test_a_timeout_ends_the_same_when_another_reaper_takes_git_s_process(
    hung_clone, blackhole, reaped_elsewhere, processes_with
):
    clone, point = hung_clone
    url, marker = point(f"http://127.0.0.1:{blackhole}/{{marker}}.git")

    gone = _Gone()
    start = time.monotonic()
    with pytest.raises(GitCliTimeoutError):
        await _fetch(clone, _source(url), timeout=_TIMEOUT, on_gone=gone)
    elapsed = time.monotonic() - start

    assert reaped_elsewhere
    await gone.wait()
    assert gone.calls == [False]
    assert elapsed <= _TIMEOUT + _GRACE + 1
    assert processes_with(marker) == []


def _state(pid: int) -> str:
    with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
        return f.read().rpartition(")")[2].split()[0]


@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="the filter reads /proc")
def test_a_group_whose_only_member_left_is_a_zombie_is_gone():
    """A zombie keeps its process group's id in use until its parent reaps it
    (pid 1, once the git that started it is gone), so the group is still there
    for kill(); but it runs nothing, and the op is over.

    A group with a live member is not.
    """
    zombie = subprocess.Popen(["true"], start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while _state(zombie.pid) != "Z":
            assert time.monotonic() < deadline, "true never exited"
            time.sleep(0.01)
        os.killpg(zombie.pid, 0)  # the group is still there
        assert git_cli.live_members(zombie.pid) is False
    finally:
        zombie.wait()
    live = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        assert git_cli.live_members(live.pid) is True
    finally:
        live.kill()
        live.wait()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS's answer to kill()")
def test_on_macos_a_group_of_zombies_kill_refuses_is_gone():
    """macOS has no /proc, and its kill() of a group whose members have all
    exited but are not reaped yet fails with EPERM: the same answer, a group
    that runs nothing.

    A group with a live member is not.
    """
    zombie = subprocess.Popen(["true"], start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                os.killpg(zombie.pid, 0)
            except PermissionError:
                break
            assert time.monotonic() < deadline, "true never exited"
            time.sleep(0.01)
        assert git_cli.live_members(zombie.pid) is False
    finally:
        zombie.wait()
    live = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        assert git_cli.live_members(live.pid) is True
    finally:
        live.kill()
        live.wait()


_PR_SET_CHILD_SUBREAPER = 36


@pytest.fixture
def subreaper(process_table):
    """This process as the subreaper of what it starts (prctl's
    PR_SET_CHILD_SUBREAPER): an orphan, which would go to pid 1, comes to it,
    and it reaps none meanwhile, so a zombie left for pid 1 stays where a test
    sees it, whatever pid 1 is.

    Those it has at the end are reaped then.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"prctl(PR_SET_CHILD_SUBREAPER): {os.strerror(err)}")
    try:
        yield
    finally:
        libc.prctl(_PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0)
        for pid, ppid, _, _ in process_table():
            if ppid != os.getpid():
                continue
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                continue  # reaped meanwhile by what started it


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="PR_SET_CHILD_SUBREAPER is Linux's"
)
@pytest.mark.asyncio
async def test_an_op_s_end_leaves_no_process_of_its_group_zombies_included(
    git_origin, tmp_path, git_groups, subreaper
):
    """sh reaps its watchdog before it exits: once the op is over, nothing of
    its group is left, not even a zombie for pid 1 to reap (this process
    stands in for pid 1 here, and reaps none).

    Ten ops: a shell not told to reap a child that died before it exits
    sometimes does so all the same.
    """
    clone = tmp_path / "cli"
    pygit2.clone_repository(git_origin.url, str(clone)).free()

    for _ in range(10):
        git_origin.commit("master")
        await _fetch(clone, _source(git_origin.url))

        with pytest.raises(ProcessLookupError):
            os.killpg(git_groups[-1].pid, 0)
    assert len(git_groups) == 10


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


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="on macOS a group's SIGKILL can miss the child sh is forking",
)
@pytest.mark.asyncio
async def test_a_hundred_timeouts_leave_the_process_and_descriptor_counts_flat(
    hung_clone, blackhole, monkeypatch, processes_with, process_table
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.2)
    clone, point = hung_clone
    url, marker = point(f"http://127.0.0.1:{blackhole}/{{marker}}.git")

    def _children() -> int:
        return sum(1 for _, ppid, _, _ in process_table() if ppid == os.getpid())

    async def _time_out() -> None:
        with pytest.raises(GitCliTimeoutError):
            await _fetch(clone, _source(url), timeout=0.05)

    await _time_out()  # what the first op sets up for good (watcher, executor)
    children, fds = _children(), _open_pipes_and_files()
    for _ in range(100):
        await _time_out()

    # <=: a child of an earlier test (a git http-backend a server thread runs)
    # may end meanwhile.
    assert _children() <= children
    assert _open_pipes_and_files() <= fds  # sh's pipes and the lock's: all closed
    assert processes_with(marker) == []
    assert git_cli.background_ops() == 0


# --- credentials -----------------------------------------------------------------


@pytest.mark.parametrize("op", ["clone", "fetch"])
@pytest.mark.parametrize("where", ["token", "url"])
@pytest.mark.asyncio
async def test_no_credential_reaches_a_command_line_an_error_or_a_log(
    op, where, git_http, make_origin, tmp_path, processes_with
):
    """A source token (sent as user ``git``, as GitCallback does) or a user
    and password in the URL: the server gets them, and no command line of
    any process (git, git-remote-http, anything else), sampled over and
    over while a clone or fetch hangs, nor any exception or log line holds
    them, in any form, when it times out or fails."""
    origin = make_origin(git_http.root / "repo.git")
    secret = f"s3cr3t{uuid.uuid4().hex}"
    if where == "token":
        url = git_http.url("repo.git")
        source = _source(url, GitHubTokenAuthData(token=secret))
        git_http.authorization = _basic("git", secret)
    else:
        url = git_http.url("repo.git", userinfo=f"alice:{secret}")
        source = _source(url)
        git_http.authorization = _basic("alice", secret)
    forms = {secret, git_http.authorization.split()[1]}
    clone = tmp_path / "cli"
    logs = []
    sink = logger.add(logs.append, level="DEBUG")
    try:
        if op == "clone":
            origin.commit("master", {"big.bin": os.urandom(1024 * 1024)})
            git_http.stall_after = 1024
            hanging = _clone(url, clone, source, timeout=1.0)
        else:
            await _clone(url, clone, source)
            assert git_http.requests
            origin.commit("master", {"big.bin": os.urandom(1024 * 1024)})
            git_http.stall_after = 1024
            hanging = _fetch(clone, source, timeout=1.0)
        task, seen, _ = await _run_and_watch(hanging, "", processes_with)
        timed_out = task.exception()
        git_http.stall_after = None
        git_http.authorization = _basic("someone", "else")
        with pytest.raises(GitCliError) as failed:
            if op == "clone":
                await _clone(url, tmp_path / "cli2", source)
            else:
                await _fetch(clone, source)
    finally:
        logger.remove(sink)

    assert isinstance(timed_out, GitCliTimeoutError)
    port = git_http.server_address[1]
    assert any(
        "remote-http" in args and f"127.0.0.1:{port}/repo.git" in args
        for _, _, args in seen
    ), seen
    texts = [args for _, _, args in seen]
    texts += [str(timed_out), str(failed.value), failed.value.stderr_tail]
    texts += [str(m) for m in logs]
    for text in texts:
        for form in forms:
            assert form not in text
    assert failed.value.returncode == 128
    assert f"127.0.0.1:{port}" in failed.value.stderr_tail


@pytest.mark.parametrize(
    "userinfo, auth, expected",
    [
        ("", GitHubTokenAuthData(token="the-token"), _basic("git", "the-token")),
        ("al%40ce:p%3Ass", None, _basic("al@ce", "p:ss")),
        ("al:pw", GitHubTokenAuthData(token="the-token"), _basic("al", "pw")),
        ("t%40ken", None, _basic("t@ken", "")),
        ("al", GitHubTokenAuthData(token="the-token"), _basic("git", "the-token")),
        ("", None, None),
    ],
    ids=["token", "url", "url-before-token", "user-only", "token-before-user", "none"],
)
@pytest.mark.asyncio
async def test_the_server_gets_the_credentials_libgit2_would_send(
    userinfo, auth, expected, git_http, make_origin, tmp_path
):
    """The server asks (401) and gets what libgit2 answers a challenge with,
    libgit2's own clone and fetch against the same server the control.

    That is the URL's user and password first (a user alone with an
    empty password), else GitCallback's UserPass("git", token). With a
    user alone and a token, libgit2 tries the user first and the token
    once the server refuses it; git asks its credential helper once,
    which gives the token. Each op's first request goes without
    credentials, as git sends them only when asked, so the credential
    helper is what answers.
    """
    origin = make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git", userinfo=userinfo)
    git_http.authorization = expected

    libgit2 = pygit2.clone_repository(
        url, str(tmp_path / "libgit2"), callbacks=GitCallback(_source(url, auth))
    )
    try:
        libgit2_clone = list(git_http.requests)
        origin.commit("master")
        libgit2.remotes["origin"].fetch(callbacks=GitCallback(_source(url, auth)))
    finally:
        libgit2.free()
    libgit2_fetch = git_http.requests[len(libgit2_clone) :]
    del git_http.requests[:]

    await _clone(url, tmp_path / "cli", _source(url, auth))
    clone_requests = list(git_http.requests)
    origin.commit("master")
    await _fetch(tmp_path / "cli", _source(url, auth))
    fetch_requests = git_http.requests[len(clone_requests) :]

    for requests in (libgit2_clone, libgit2_fetch):
        assert requests[-1][2].get("Authorization") == expected
    for requests in (clone_requests, fetch_requests):
        sent = [h.get("Authorization") for _, _, h in requests]
        if expected is None:
            assert set(sent) == {None}
        else:
            assert sent[0] is None and sent[-1] == expected
            assert set(sent) == {None, expected}


@pytest.mark.parametrize("target_asks", [False, True], ids=["open", "asks"])
@pytest.mark.asyncio
async def test_a_redirect_to_another_host_gets_no_credentials(
    target_asks, git_http, make_git_http, make_origin, tmp_path
):
    """The remote redirects to another host and port.

    git asks its credential helper per host, and the helper answers only
    for the remote's own host and port, so the other host never gets the
    token, whether it asks for credentials or not.
    """
    other = make_git_http(tmp_path / "other")
    make_origin(other.root / "repo.git")
    git_http.redirect_to = other.url("")
    other.authorization = _basic("git", "the-token") if target_asks else None
    url = git_http.url("repo.git")
    source = _source(url, GitHubTokenAuthData(token="the-token"))

    if target_asks:
        with pytest.raises(GitCliError):
            await _clone(url, tmp_path / "cli", source)
    else:
        await _clone(url, tmp_path / "cli", source)
        assert "refs/remotes/origin/master" in _refs(tmp_path / "cli")

    assert git_http.requests and other.requests
    assert [h.get("Authorization") for _, _, h in other.requests] == [None] * len(
        other.requests
    )


@pytest.mark.parametrize("where", ["token", "url"])
@pytest.mark.asyncio
async def test_an_http_remote_that_redirects_to_https_on_its_host_gets_its_credentials(
    where, git_http, tls_cert, make_origin, tmp_path, monkeypatch
):
    """An http:// source whose server redirects every request to https:// on
    the same host and port, and asks for credentials there.

    git asks its credential helper for https after the redirect, and
    gets the source's credentials; they are never sent over plain http.
    """
    origin = make_origin(git_http.root / "repo.git")
    git_http.tls = tls_cert.context
    git_http.redirect_to = git_http.url("", scheme="https")
    monkeypatch.setenv("GIT_SSL_CAINFO", str(tls_cert.path))
    if where == "token":
        url = git_http.url("repo.git")
        source = _source(url, GitHubTokenAuthData(token="the-token"))
        git_http.authorization = _basic("git", "the-token")
    else:
        url = git_http.url("repo.git", userinfo="alice:pw")
        source = _source(url)
        git_http.authorization = _basic("alice", "pw")

    await _clone(url, tmp_path / "cli", source)
    head = origin.commit("master")
    await _fetch(tmp_path / "cli", source)

    assert _refs(tmp_path / "cli")["refs/remotes/origin/master"] == head
    auths = [h.get("Authorization") for _, _, h in git_http.requests]
    sent = list(zip(git_http.schemes, auths))
    assert ("http", None) in sent
    assert ("https", git_http.authorization) in sent
    assert {auth for scheme, auth in sent if scheme == "http"} == {None}


@pytest.mark.asyncio
async def test_the_token_is_in_no_git_config_or_command_line_given_to_git(
    git_http, make_origin, tmp_path, monkeypatch
):
    """The credential helper in git's environment config reads the token from a
    variable of git's environment: neither the helper's text, nor any other
    config git is given, nor git's command line, nor the clone's config holds
    it."""
    make_origin(git_http.root / "repo.git")
    token = f"tok{uuid.uuid4().hex}"
    url = git_http.url("repo.git")
    git_http.authorization = _basic("git", token)
    seen = tmp_path / "seen"
    real_git = shutil.which("git")
    _shim(
        tmp_path,
        monkeypatch,
        "git",
        f"env | grep '^GIT_CONFIG' >> '{seen}'\n"
        f"echo \"args: $*\" >> '{seen}'\n"
        f'exec "{real_git}" "$@"',
    )

    await _clone(url, tmp_path / "cli", _source(url, GitHubTokenAuthData(token=token)))

    given = seen.read_text()
    assert "credential.helper" in given and "args: " in given
    assert token not in given
    for path in (tmp_path / "cli" / ".git").rglob("*"):
        if path.is_file():
            assert token.encode() not in path.read_bytes(), path


_HTTP_REMOTE = "http://git.example:8080/org/repo.git"
_HTTPS_REMOTE = "https://git.example:8080/org/repo.git"


@pytest.mark.parametrize(
    "url, asked, answers",
    [
        (_HTTP_REMOTE, "protocol=http\nhost=git.example:8080\n", True),
        (
            _HTTP_REMOTE,
            "protocol=http\nhost=git.example:8080\npath=other/r.git\n",
            True,
        ),
        (_HTTP_REMOTE, "protocol=https\nhost=git.example:8080\n", True),
        (_HTTP_REMOTE, "protocol=http\nhost=git.example\n", False),
        (_HTTP_REMOTE, "protocol=http\nhost=elsewhere.example:8080\n", False),
        (_HTTP_REMOTE, "protocol=https\nhost=git.example\n", False),
        (_HTTP_REMOTE, "protocol=https\nhost=elsewhere.example:8080\n", False),
        (_HTTPS_REMOTE, "protocol=https\nhost=git.example:8080\n", True),
        (_HTTPS_REMOTE, "protocol=http\nhost=git.example:8080\n", False),
    ],
    ids=[
        "its-host",
        "other-path",
        "https-on-its-host",
        "other-port",
        "other-host",
        "https-other-port",
        "https-other-host",
        "https-remote",
        "https-remote-asked-for-http",
    ],
)
def test_the_credential_helper_answers_only_for_the_remote_s_protocol_and_host(
    url, asked, answers, tmp_path
):
    """What git asks its credential helpers, asked of git itself (git
    credential fill) with the environment an op gives git: the user and
    password come back for the remote's own host:port, any path
    (credential.useHttpPath is off), over the remote's protocol or, for an
    http remote, https (where a redirect to https on its host takes git),
    and for nothing else: not another host or port, a redirect's target
    included, and not http for an https remote."""
    source = _source(url, GitHubTokenAuthData(token="the-token"))
    remote = git_cli._remote_for_git(url, source)
    with git_cli._git_env(source, remote) as (env, _):
        filled = subprocess.run(
            ["git", "credential", "fill"],
            input=asked + "\n",
            env=env,
            capture_output=True,
            text=True,
            cwd=tmp_path,  # outside any repository
        )

    if answers:
        assert filled.returncode == 0, filled.stderr
        assert "username=git\n" in filled.stdout
        assert "password=the-token\n" in filled.stdout
    else:
        assert filled.returncode != 0
        assert "the-token" not in filled.stdout + filled.stderr


@pytest.mark.parametrize("where", ["token", "url"])
@pytest.mark.asyncio
async def test_what_the_server_says_back_is_redacted_from_git_s_errors(
    where, git_http, make_origin, tmp_path
):
    """A server that echoes the credential it was given in its error, which git
    prints as is (``fatal: remote error: ...``): the error, its stderr tail and
    its message show *** in its place, in every form."""
    make_origin(git_http.root / "repo.git")
    secret = f"s3cr3t{uuid.uuid4().hex}"
    if where == "token":
        url = git_http.url("repo.git")
        source = _source(url, GitHubTokenAuthData(token=secret))
        git_http.authorization = _basic("git", secret)
    else:
        url = git_http.url("repo.git", userinfo=f"alice:{secret}")
        source = _source(url)
        git_http.authorization = _basic("alice", secret)
    header = git_http.authorization
    git_http.error = f"no access for {secret}, sent as {header}"

    with pytest.raises(GitCliError) as info:
        await _clone(url, tmp_path / "cli", source)

    tail = info.value.stderr_tail
    assert "remote error" in tail
    assert tail.count("***") >= 2
    for text in (tail, str(info.value)):
        assert secret not in text
        assert header.split()[1] not in text


def _failing_git(tmp_path: Path, monkeypatch, stderr: str) -> None:
    """Put a git first on PATH that writes ``stderr`` and exits 128."""
    text = tmp_path / "stderr.txt"
    text.write_text(stderr)
    _shim(tmp_path, monkeypatch, "git", f"cat '{text}' >&2\nexit 128")


def _shows_part_of(secret: str, text: str) -> bool:
    return any(secret[i : i + 8] in text for i in range(len(secret) - 7))


@pytest.mark.parametrize(
    "url, token, stderr, shown",
    [
        (
            "ssh://git@github.com/acme/repo.git",
            None,
            "ssh: connect to host github.com port 22: Connection refused\n"
            "fatal: 'acme/repo.git' does not appear to be a git repository",
            "ssh: connect to host github.com port 22: Connection refused\n"
            "fatal: 'acme/repo.git' does not appear to be a git repository",
        ),
        (
            "https://git:mygitpass@127.0.0.1/r.git",
            None,
            "fatal: git was refused mygitpass",
            "fatal: git was refused ***",
        ),
        (
            "https://alice:s3cret@127.0.0.1/r.git",
            None,
            "fatal: alice was refused s3cret",
            "fatal: alice was refused ***",
        ),
        (
            "https://t0ken@127.0.0.1/r.git",
            None,
            "fatal: t0ken was refused",
            "fatal: *** was refused",
        ),
        (
            "https://tok@127.0.0.1/r.git",
            "tok-and-more",
            "fatal: tok-and-more was refused",
            "fatal: *** was refused",
        ),
        (
            "https://git@127.0.0.1/r.git",
            None,
            "fatal: 'r.git' does not appear to be a git repository",
            "fatal: 'r.git' does not appear to be a git repository",
        ),
        (
            "https://t0kenvalue:x-oauth-basic@127.0.0.1/r.git",
            None,
            "fatal: t0kenvalue was refused",
            "fatal: *** was refused",
        ),
        (
            "https://ci@127.0.0.1/r.git",
            None,
            "fatal: circuit open for ci; ci-runner, cigar",
            "fatal: circuit open for ***; ***-runner, cigar",
        ),
        (
            "https://tok:127@127.0.0.1:8127/r.git",
            None,
            "fatal: unable to access 'https://127.0.0.1:8127/r.git/': 127 refused\n"
            "fatal: could not connect to 127.0.0.1 port 8127: 127",
            "fatal: unable to access 'https://127.0.0.1:8127/r.git/': *** refused\n"
            "fatal: could not connect to 127.0.0.1 port 8127: ***",
        ),
        (
            "https://alice:s3cret@127.0.0.1/r.git",
            None,
            "fatal: refused s3cretXs3cret",
            "fatal: refused ***X***",
        ),
    ],
    ids=[
        "ssh-user-git",
        "git-and-password",
        "user-and-password",
        "user-alone",
        "longest",
        "git-alone",
        "token-as-user",
        "short-user-alone",
        "password-in-the-host",
        "inside-a-word",
    ],
)
@pytest.mark.asyncio
async def test_what_can_be_a_credential_is_redacted_from_git_s_errors_and_no_more(
    url, token, stderr, shown, tmp_path, monkeypatch
):
    """A URL's password and a source's token, wherever they are, so that no
    part of one is left; the user of a URL whose password is x-oauth-basic
    (GitHub's form for a token as the user); and a user alone in an HTTP URL
    (which can be a token) where it is a word of its own.

    Not the user of a URL with another password, nor ``git`` (the user
    of every SSH URL to GitHub, and a word of git's errors and of its
    hosts' names), nor a user alone inside a longer word, nor the URL
    git is given or its host, which hold no credential even where a
    password's text is part of them.
    """
    _failing_git(tmp_path, monkeypatch, stderr)
    auth = GitHubTokenAuthData(token=token) if token else None

    with pytest.raises(GitCliError) as info:
        await _clone(url, tmp_path / "cli", _source(url, auth))

    assert info.value.stderr_tail == shown


@pytest.mark.parametrize(
    "url, text, shown",
    [
        ("https://alice:zz@127.0.0.1/r.git", "refused zzz", "refused ***"),
        ("https://ci@127.0.0.1/r.git", "ci failed", "*** failed"),
        ("https://ci@127.0.0.1/r.git", "pci, then ci", "pci, then ***"),
        ("https://ci@127.0.0.1/r.git", "ci2 failed", "ci2 failed"),
        ("https://ci-@127.0.0.1/r.git", "ci-x", "***x"),
        ("https://-ci@127.0.0.1/r.git", "x-ci", "x***"),
        ("https://ci@127.0.0.1/r.git", "-" * 300 + " ci", "-" * 300 + " ***"),
    ],
    ids=[
        "overlapping",
        "word-at-the-start",
        "word-at-the-end",
        "longer-word-at-the-start",
        "ends-in-punctuation",
        "starts-with-punctuation",
        "word-at-the-end-of-a-long-text",
    ],
)
def test_redaction_at_the_edges_of_the_text_and_of_words(url, text, shown):
    """A password is redacted wherever it is, places that overlap included
    (``zz`` twice in ``zzz``), so that no part of it is left.

    A user alone is redacted where it is a word of its own: at the very
    start or end of the text, however long the text, and where its own
    punctuation meets a letter; not where a letter or digit runs on into
    it (``pci``, ``ci2``).
    """
    assert git_cli._remote_for_git(url, _source(url)).redact(text) == shown


@pytest.mark.parametrize(
    "password, redacted",
    [
        ("x-oauth-basic", True),
        ("X-OAuth-Basic", True),
        ("x-oauth-basic2", False),
        ("zebra", False),
    ],
)
def test_the_user_is_a_secret_only_with_the_password_x_oauth_basic(password, redacted):
    """GitHub's form for a token as the user has the password x-oauth-basic,
    in any case: the user is then redacted. With any other password, however
    close, the user is no secret and shows."""
    url = f"https://t0kenvalue:{password}@127.0.0.1/r.git"
    remote = git_cli._remote_for_git(url, _source(url))

    shown = remote.redact("fatal: t0kenvalue was refused")

    user = "***" if redacted else "t0kenvalue"
    assert shown == f"fatal: {user} was refused"


@pytest.mark.parametrize("cut", ["tail", "kept"])
@pytest.mark.asyncio
async def test_no_part_of_a_secret_cut_by_the_error_s_length_limits_shows(
    cut, tmp_path, monkeypatch
):
    """An error quotes the last _STDERR_TAIL_CHARS characters of git's stderr,
    of which only the last four times that many bytes are kept.

    A password that either cut goes through shows no part of itself:
    redacted before the tail is cut, and, where the kept bytes start in
    the middle of a line, that line is dropped (here the password fills
    every line, so what is kept is far shorter than the tail once
    redacted).
    """
    secret = f"s3cr3t{uuid.uuid4().hex}"
    url = f"https://alice:{secret}@127.0.0.1/r.git"
    tail = git_cli._STDERR_TAIL_CHARS
    if cut == "tail":
        stderr = "x" * 100 + secret + "y" * (tail - len(secret) // 2)
    else:
        line, kept = secret + "\n", 4 * tail
        lines = 2 * kept // len(line)
        pad = (len(line) // 2 - (lines * len(line) - kept)) % len(line)
        stderr = line * lines + "p" * pad
    _failing_git(tmp_path, monkeypatch, stderr)

    with pytest.raises(GitCliError) as info:
        await _clone(url, tmp_path / "cli", _source(url))

    assert "***" in info.value.stderr_tail
    for text in (info.value.stderr_tail, str(info.value)):
        assert not _shows_part_of(secret, text), text


@pytest.mark.parametrize(
    "password, repo",
    [("x", "policy-x.git"), ("127", "repo.git")],
    ids=["in-the-path", "in-the-host"],
)
@pytest.mark.asyncio
async def test_a_password_whose_text_is_elsewhere_in_the_url_is_still_used(
    password, repo, git_http, make_origin, tmp_path
):
    """The URL given to git keeps no password, whatever its path or host
    holds: a password whose text appears there is not refused, and the
    server gets it, as libgit2 sends it."""
    make_origin(git_http.root / repo)
    url = git_http.url(repo, userinfo=f"tok:{password}")
    git_http.authorization = _basic("tok", password)

    await _clone(url, tmp_path / "cli", _source(url))

    assert "refs/remotes/origin/master" in _refs(tmp_path / "cli")


@pytest.mark.parametrize(
    "userinfo, token",
    [("alice:a%0Ab", None), ("alice:a%00b", None), ("", "to\0ken")],
    ids=["newline", "NUL-in-the-url", "NUL-in-the-token"],
)
@pytest.mark.asyncio
async def test_a_credential_with_a_newline_or_a_nul_is_refused(
    userinfo, token, git_http, tmp_path
):
    """git's credential protocol cannot carry a newline, and no environment
    variable can hold a NUL: such a user, password or token is refused as the
    source's, before git runs, with git's status for a fatal error."""
    url = git_http.url("repo.git", userinfo=userinfo)
    auth = GitHubTokenAuthData(token=token) if token else None

    with pytest.raises(GitCliRefusedSourceError, match="newline or a NUL") as info:
        await _clone(url, tmp_path / "cli", _source(url, auth))

    assert info.value.returncode == 128
    assert git_http.requests == []


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_FAKE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nbm90IGEga2V5\n-----END OPENSSH PRIVATE KEY-----"


@pytest.mark.parametrize("op", ["clone", "fetch"])
@pytest.mark.asyncio
async def test_the_ssh_key_is_in_a_private_file_removed_after_a_kill_or_failure(
    op, hung_clone, blackhole, tmp_path, monkeypatch, processes_with
):
    """0600, in a 0700 directory of its own named after this process, in memory
    (/dev/shm) where there is one, while git runs, and on no command line (ssh
    gets the file's path), nor is the URL's password; gone once the op has
    returned, killed or failed."""
    keys = tmp_path / "shm"
    keys.mkdir()
    monkeypatch.setattr(git_cli, "_SHM", str(keys))
    disk = tmp_path / "tmp"
    disk.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(disk))
    clone, point = hung_clone
    url, marker = point(
        f"ssh://git:urlpw{uuid.uuid4().hex}@127.0.0.1:{blackhole}/{{marker}}.git"
    )
    password = url.split(":")[2].split("@")[0]
    source = _source(url, SSHAuthData(username="git", private_key=_FAKE_KEY))
    seen = []
    command_lines = set()

    async def _look():
        while True:
            for d in keys.iterdir():
                for f in d.iterdir():
                    seen.append(
                        (
                            d.name,
                            stat.S_IMODE(d.stat().st_mode),
                            stat.S_IMODE(f.stat().st_mode),
                            f.read_text(),
                        )
                    )
            command_lines.update(a for _, _, a in processes_with(""))
            await asyncio.sleep(0.02)

    looker = asyncio.ensure_future(_look())
    try:
        with pytest.raises(GitCliTimeoutError):
            if op == "clone":
                await _clone(url, tmp_path / "new", source, timeout=_HUNG_TIMEOUT)
            else:
                await _fetch(clone, source, timeout=_HUNG_TIMEOUT)
    finally:
        looker.cancel()

    assert seen
    for name, dir_mode, file_mode, content in seen:
        assert name.startswith(f"opal-git-ssh-{os.getpid()}-")
        assert (dir_mode, file_mode) == (0o700, 0o600)
        assert content == _FAKE_KEY + "\n"
    assert list(keys.iterdir()) == [] and list(disk.iterdir()) == []
    assert any(marker in a and str(keys) in a for a in command_lines)
    assert not any("bm90IGEga2V5" in a or password in a for a in command_lines)

    _point_at(clone, f"ssh://git@127.0.0.1:{_closed_port()}/repo.git")
    with pytest.raises(GitCliError):
        await _fetch(clone, source, timeout=30)
    assert list(keys.iterdir()) == []


def test_ssh_key_files_go_to_dev_shm_only_where_it_is_a_writable_directory(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    shm = tmp_path / "shm"
    monkeypatch.setattr(git_cli, "_SHM", str(shm))
    assert git_cli._key_dir_parent() == str(tmp_path / "tmp")
    shm.write_text("")
    assert git_cli._key_dir_parent() == str(tmp_path / "tmp")
    shm.unlink()
    shm.mkdir()
    assert git_cli._key_dir_parent() == str(shm)
    shm.chmod(0o500)
    try:
        if not os.access(shm, os.W_OK):
            assert git_cli._key_dir_parent() == str(tmp_path / "tmp")
    finally:
        shm.chmod(0o700)


def _open_directories() -> set:
    """This process's fds open on directories, as (fd, device, inode); compare
    with ``<=``, as for _open_pipes_and_files."""
    found = set()
    for name in os.listdir("/dev/fd"):
        try:
            st = os.fstat(int(name))
        except OSError as e:
            if e.errno != errno.EBADF:
                raise
            continue  # closed since the listing: the listing's own
        if stat.S_ISDIR(st.st_mode):
            found.add((int(name), st.st_dev, st.st_ino))
    return found


def test_an_ssh_key_dir_whose_lock_fails_is_removed_and_fails_the_op_locally(
    tmp_path, monkeypatch
):
    """Where the filesystem the key files go to refuses an flock (ENOLCK), the
    op's key directory cannot be held against the sweep: it is removed, its fd
    closed, and the op fails as a local error before git runs."""
    keys = tmp_path / "shm"
    keys.mkdir()
    monkeypatch.setattr(git_cli, "_SHM", str(keys))
    url = "ssh://git@127.0.0.1:22/repo.git"
    source = _source(url, SSHAuthData(username="git", private_key=_FAKE_KEY))
    directories = _open_directories()
    _flock_fails_with(monkeypatch, errno.ENOLCK)

    with pytest.raises(GitCliLocalError, match="cannot write the SSH key file"):
        with git_cli._git_env(source, git_cli._remote_for_git(url, source)):
            pass

    assert list(keys.iterdir()) == []
    assert _open_directories() <= directories


def test_the_ssh_command_never_falls_back_to_the_server_user_s_own_keys(tmp_path):
    """IdentityFile=none comes before any -i: no key of ~/.ssh is tried, with
    the op's own key or without one (libgit2 uses only the source's)."""
    url = "ssh://git@127.0.0.1:22/repo.git"
    for auth in (None, SSHAuthData(username="git", private_key=_FAKE_KEY)):
        source = _source(url, auth)
        with git_cli._git_env(source, git_cli._remote_for_git(url, source)) as (env, _):
            ssh = shlex.split(env["GIT_SSH_COMMAND"])
        assert "IdentityFile=none" in ssh
        if auth is not None:
            assert ssh.index("IdentityFile=none") < ssh.index("-i")


@pytest.mark.asyncio
async def test_the_ssh_git_runs_ends_a_silent_link_on_its_own(
    git_origin, tmp_path, monkeypatch
):
    """The ssh git runs gives up on a connect after 30 s, and on a link the
    server stays silent on after 4 keepalives 15 s apart (about a minute), with
    an error of its own rather than at the op's timeout."""
    argv = tmp_path / "ssh.argv"
    _shim(tmp_path, monkeypatch, "ssh", f'printf "%s\\n" "$@" > "{argv}"\nexit 255')
    clone = tmp_path / "cli"
    pygit2.clone_repository(git_origin.url, str(clone)).free()
    url = "ssh://git@127.0.0.1:1/repo.git"
    _point_at(clone, url)

    with pytest.raises(GitCliError):
        await _fetch(clone, _source(url))

    ssh = argv.read_text().splitlines()
    for option in (
        "ConnectTimeout=30",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=4",
    ):
        assert ssh[ssh.index(option) - 1] == "-o", ssh


@pytest.mark.parametrize("known_hosts", [False, True], ids=["as-libgit2", "file"])
@pytest.mark.asyncio
async def test_the_ssh_git_runs_reads_no_ssh_config_and_no_system_known_hosts(
    known_hosts, git_origin, tmp_path, monkeypatch
):
    """The ssh git runs is given -F /dev/null and
    GlobalKnownHostsFile=/dev/null, with SCOPES_GIT_SSH_KNOWN_HOSTS too.

    Without them it would read /etc/ssh/ssh_config, ssh_config.d and the
    server user's ~/.ssh/config (its home comes from the user database,
    not HOME), which can bring a ProxyCommand, a ControlMaster, an
    IdentityFile or SendEnv to every op; and it would trust the host
    keys of /etc/ssh/ssh_known_hosts beside those of the configured
    file.
    """
    argv = tmp_path / "ssh.argv"
    _shim(tmp_path, monkeypatch, "ssh", f'printf "%s\\n" "$@" > "{argv}"\nexit 255')
    if known_hosts:
        path = tmp_path / "known_hosts"
        path.write_text("")
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))
    clone = tmp_path / "cli"
    pygit2.clone_repository(git_origin.url, str(clone)).free()
    url = "ssh://git@127.0.0.1:1/repo.git"
    _point_at(clone, url)

    with pytest.raises(GitCliError):
        await _fetch(clone, _source(url))

    ssh = argv.read_text().splitlines()
    assert ssh[ssh.index("-F") + 1] == "/dev/null", ssh
    assert ssh[ssh.index("GlobalKnownHostsFile=/dev/null") - 1] == "-o", ssh
    if known_hosts:
        assert f"UserKnownHostsFile={path}" in ssh, ssh


@pytest.mark.asyncio
async def test_git_speaks_protocol_v2_whatever_the_clone_s_config_says(
    http_clone, git_http
):
    """Protocol v2 is git's default; a clone's own config, which git reads,
    could set another."""
    _, url, clone, _ = http_clone
    subprocess.run(
        ["git", "-C", str(clone), "config", "protocol.version", "1"], check=True
    )
    git_http.requests.clear()

    await _fetch(clone, _source(url))

    protocols = [headers.get("Git-Protocol") for _, _, headers in git_http.requests]
    assert "version=2" in protocols, protocols
    assert "version=1" not in protocols, protocols


@pytest.mark.asyncio
async def test_a_clone_over_ssh_with_a_key_works_and_removes_the_key(
    sshd, make_origin, tmp_path, monkeypatch
):
    keys = tmp_path / "shm"
    keys.mkdir()
    monkeypatch.setattr(git_cli, "_SHM", str(keys))
    origin = make_origin(tmp_path / "served" / "repo.git")
    url = sshd.url(origin.path)
    source = _source(url, SSHAuthData(username="git", private_key=sshd.client_key))

    await _clone(url, tmp_path / "cli", source)
    head = origin.commit("master")
    await _fetch(tmp_path / "cli", source)

    assert _refs(tmp_path / "cli")["refs/remotes/origin/master"] == head
    assert _remote_urls(tmp_path / "cli") == [("origin", url)]
    assert list(keys.iterdir()) == []


@pytest.mark.asyncio
async def test_an_ssh_rsa_only_server_fails_with_ssh_s_reason_in_the_error(
    make_sshd, make_origin, tmp_path
):
    """A server that offers only an ssh-rsa (SHA-1) host key, which ssh from
    OpenSSH 8.8 on refuses and libgit2 (the control, on the same server)
    accepts: ssh says why at its INFO level, and the error has that line, not
    only git's "Could not read from remote repository"."""
    server = make_sshd(host_key_type="rsa", config="HostKeyAlgorithms ssh-rsa\n")
    origin = make_origin(tmp_path / "served" / "repo.git")
    url = server.url(origin.path)
    source = _source(url, SSHAuthData(username="git", private_key=server.client_key))

    libgit2 = _libgit2_ssh_clone(url, tmp_path / "libgit2", server.client_key)
    with pytest.raises(GitCliError) as info:
        await _clone(url, tmp_path / "cli", source)

    assert libgit2 == "accepted", libgit2
    assert "no matching host key type found. Their offer: ssh-rsa" in (
        info.value.stderr_tail
    )


def _server_sig_algs(server, key: Path) -> list:
    """The signature algorithms for users' keys that ``server`` advertises (its
    server-sig-algs), as ssh logs them at debug level."""
    done = subprocess.run(
        [
            "ssh",
            "-vv",
            "-F",
            "/dev/null",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "IdentitiesOnly=yes",
            "-i",
            str(key),
            "-p",
            str(server.port),
            "127.0.0.1",
            "true",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    found = re.search(r"server-sig-algs=<([^>]*)>", done.stderr)
    assert found, done.stderr
    return found.group(1).split(",")


@pytest.mark.parametrize("server_takes", ["ssh-rsa only", "any"])
@pytest.mark.asyncio
async def test_an_rsa_user_key_where_a_server_takes_only_ssh_rsa_signatures(
    server_takes, make_sshd, make_origin, tmp_path
):
    """A server that takes only ssh-rsa (SHA-1) signatures of a user's key
    (PubkeyAcceptedAlgorithms ssh-rsa), and a user's RSA key: ssh refuses to
    sign with ssh-rsa, so git fails here whatever the server advertises.

    libgit2 (the control, on the same server) signs with the first of
    rsa-sha2-512, rsa-sha2-256 and ssh-rsa that the server advertises
    for users' keys. Measured: OpenSSH 9.2's sshd advertises rsa-sha2-*
    too and then refuses them, and libgit2 fails as well; OpenSSH 10.0's
    advertises only what it takes, and libgit2 gets in. The same key
    works with both against a server that takes any signature.
    """
    config = "PubkeyAcceptedAlgorithms ssh-rsa\n" if server_takes != "any" else ""
    server = make_sshd(config=config)
    rsa = tmp_path / "rsa"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "rsa", "-b", "2048", "-N", "", "-f", str(rsa)],
        check=True,
        capture_output=True,
    )
    (server.base / "authorized_keys").write_text((tmp_path / "rsa.pub").read_text())
    origin = make_origin(tmp_path / "served" / "repo.git")
    url = server.url(origin.path)
    source = _source(url, SSHAuthData(username="git", private_key=rsa.read_text()))

    advertised = _server_sig_algs(server, rsa)
    libgit2 = _libgit2_ssh_clone(url, tmp_path / "libgit2", rsa.read_text())
    if server_takes == "any":
        await _clone(url, tmp_path / "cli", source)
        assert libgit2 == "accepted", libgit2
        assert "refs/remotes/origin/master" in _refs(tmp_path / "cli")
        return
    with pytest.raises(GitCliError) as info:
        await _clone(url, tmp_path / "cli", source)
    assert "Permission denied (publickey)" in info.value.stderr_tail
    libgit2_signs_ssh_rsa = not {"rsa-sha2-512", "rsa-sha2-256"} & set(advertised)
    assert libgit2.startswith("accepted" if libgit2_signs_ssh_rsa else "rejected"), (
        advertised,
        libgit2,
    )


@pytest.mark.asyncio
async def test_an_ssh_error_does_not_say_the_host_key_was_added(
    sshd, make_origin, tmp_path
):
    """Without SCOPES_GIT_SSH_KNOWN_HOSTS ssh takes the server's host key and,
    on every op, says it added it to known_hosts, which is /dev/null: the error
    (here for a key the server does not authorize) leaves that out."""
    origin = make_origin(tmp_path / "served" / "repo.git")
    url = sshd.url(origin.path)
    unauthorized = (sshd.base / "other_host_key").read_text()
    source = _source(url, SSHAuthData(username="git", private_key=unauthorized))

    with pytest.raises(GitCliError) as info:
        await _clone(url, tmp_path / "cli", source)

    assert "Permission denied (publickey)" in info.value.stderr_tail
    assert "Permanently added" not in info.value.stderr_tail


@pytest.mark.asyncio
async def test_the_error_keeps_ssh_s_reason_and_drops_its_host_key_note(
    tmp_path, monkeypatch
):
    """What ssh writes, each line ending in CRLF as ssh ends it: the error
    keeps why the op failed (a link the server went silent on, here) and drops
    the host-key note every op without a known_hosts file gets."""
    _shim(
        tmp_path,
        monkeypatch,
        "ssh",
        r"""printf "Warning: Permanently added '[127.0.0.1]:1' (ED25519) to the list of known hosts.\r\n" >&2
printf 'Timeout, server 127.0.0.1 not responding.\r\n' >&2
exit 255""",
    )
    url = "ssh://git@127.0.0.1:1/repo.git"

    with pytest.raises(GitCliError) as info:
        await _clone(url, tmp_path / "cli")

    assert "Timeout, server 127.0.0.1 not responding." in info.value.stderr_tail
    assert "Permanently added" not in info.value.stderr_tail


# --- SSH host keys -------------------------------------------------------------

_LIBGIT2_CLONE = """
import sys
import pygit2
from opal_common.schemas.policy_source import GitPolicyScopeSource, SSHAuthData
from opal_server.git_fetcher import GitCallback

source = GitPolicyScopeSource(
    source_type="git",
    url=sys.argv[1],
    branch="master",
    auth=SSHAuthData(username="git", private_key=open(sys.argv[3]).read()),
)
try:
    pygit2.clone_repository(sys.argv[1], sys.argv[2], callbacks=GitCallback(source)).free()
    print("accepted")
except pygit2.GitError as e:
    print("rejected:", e)
"""


def _libgit2_ssh_clone(
    url: str, dest: Path, key: str, home: Optional[Path] = None
) -> str:
    """The control: ``url`` cloned to ``dest`` by libgit2 with the private
    key ``key``, as the scopes fetcher clones (GitCallback), in a child
    interpreter, whose HOME is ``home`` when given (libgit2 reads HOME once,
    as it loads). What it printed: "accepted", or "rejected: ..."."""
    key_file = dest.parent / f"{dest.name}.key"
    key_file.write_text(key)
    env = dict(os.environ) if home is None else {**os.environ, "HOME": str(home)}
    done = subprocess.run(
        [sys.executable, "-c", _LIBGIT2_CLONE, url, str(dest), str(key_file)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return done.stdout.strip() or done.stderr.strip()


_KNOWN_HOSTS_CASES = [
    "no file",
    "another host only",
    "this host, its key",
    "this host, another key",
]


def _known_hosts(sshd, case: str):
    entry = f"[127.0.0.1]:{sshd.port}"
    return {
        "no file": None,
        "another host only": f"[127.0.0.2]:{sshd.port} {sshd.public_key('host_key')}\n",
        "this host, its key": f"{entry} {sshd.public_key('host_key')}\n",
        "this host, another key": f"{entry} {sshd.public_key('other_host_key')}\n",
    }[case]


@pytest.mark.parametrize("known_hosts", _KNOWN_HOSTS_CASES)
@pytest.mark.asyncio
async def test_ssh_host_keys_get_the_answer_libgit2_gives(
    known_hosts, sshd, make_origin, tmp_path, monkeypatch
):
    """Measured with pygit2 1.21.0 and libgit2 1.9.7 against this sshd, with
    $HOME/.ssh/known_hosts (the file libgit2 reads) holding:

    ==========================  ===========  ======================
    known_hosts                 libgit2      ssh's defaults
                                             (BatchMode=yes)
    ==========================  ===========  ======================
    no file                     accepted     rejected
    another host only           accepted     rejected
    this host, its key          accepted     accepted
    this host, another key      accepted     rejected
    ==========================  ===========  ======================

    libgit2 writes nothing to the file in any case. pygit2's certificate
    callback answers "accept" for every libssh2 host key when the callbacks
    (GitCallback) do not override certificate_check, so libgit2's own
    verdict from known_hosts is not used. Without SCOPES_GIT_SSH_KNOWN_HOSTS
    the options git_cli gives ssh accept all four too, and write no
    known_hosts file either: the CLI backend accepts the hosts the libgit2
    one does. libgit2 runs in a child interpreter here because it reads
    $HOME once, when it loads.
    """
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    contents = _known_hosts(sshd, known_hosts)
    known = home / ".ssh" / "known_hosts"
    if contents is not None:
        known.write_text(contents)
    origin = make_origin(tmp_path / "served" / "repo.git")
    url = sshd.url(origin.path)

    libgit2 = _libgit2_ssh_clone(url, tmp_path / "libgit2", sshd.client_key, home)
    monkeypatch.setenv("HOME", str(home))
    await _clone(
        url,
        tmp_path / "cli",
        _source(url, SSHAuthData(username="git", private_key=sshd.client_key)),
    )

    assert libgit2 == "accepted", libgit2
    assert "refs/remotes/origin/master" in _refs(tmp_path / "cli")
    assert (known.read_text() if known.exists() else None) == contents


@pytest.mark.parametrize(
    "known_hosts, accepted",
    [
        ("this host, its key", True),
        ("another host only", False),
        ("this host, another key", False),
    ],
)
@pytest.mark.asyncio
async def test_with_a_known_hosts_file_only_a_host_with_its_key_in_it_is_accepted(
    known_hosts, accepted, sshd, make_origin, tmp_path, monkeypatch
):
    """SCOPES_GIT_SSH_KNOWN_HOSTS: the git host's SSH key is verified against
    that file, which is never written to."""
    path = tmp_path / "known_hosts"
    contents = _known_hosts(sshd, known_hosts)
    path.write_text(contents)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))
    validate_git_cli_settings()
    origin = make_origin(tmp_path / "served" / "repo.git")
    url = sshd.url(origin.path)
    source = _source(url, SSHAuthData(username="git", private_key=sshd.client_key))

    if accepted:
        await _clone(url, tmp_path / "cli", source)
        await _fetch(tmp_path / "cli", source)
        assert "refs/remotes/origin/master" in _refs(tmp_path / "cli")
    else:
        with pytest.raises(GitCliError) as info:
            await _clone(url, tmp_path / "cli", source)
        assert "Host key verification failed" in info.value.stderr_tail
        assert not (tmp_path / "cli").exists()
    assert path.read_text() == contents


@pytest.mark.parametrize(
    "url_format",
    ["ssh://git@127.0.0.1:{port}/{marker}.git", "git@127.0.0.1:{marker}.git"],
    ids=["ssh-url", "scp-like"],
)
@pytest.mark.parametrize("problem", ["missing", "unreadable", "a directory"])
@pytest.mark.asyncio
async def test_a_known_hosts_file_that_cannot_be_read_fails_fast(
    problem, url_format, git_origin, tmp_path, monkeypatch, processes_with
):
    """At startup, and at every SSH op after that (the file can go away
    meanwhile), before any git runs, whether the source's URL is ssh:// or
    git's scp-like ``user@host:path``."""
    path = tmp_path / "known_hosts"
    if problem == "unreadable":
        path.write_text("")
        path.chmod(0)
        if os.access(path, os.R_OK):
            pytest.skip("this user reads every file (root)")
    elif problem == "a directory":
        path.mkdir()
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))
    marker = f"never-{uuid.uuid4().hex}"
    url = url_format.format(port=_closed_port(), marker=marker)

    with pytest.raises(ValueError, match="no readable file"):
        validate_git_cli_settings()
    task, seen, elapsed = await _run_and_watch(
        _clone(url, tmp_path / "cli"), marker, processes_with
    )

    assert isinstance(task.exception(), GitCliLocalError)
    assert "no readable file" in task.exception().stderr_tail
    assert seen == set()
    # An HTTP or local source does not use the file.
    await _clone(git_origin.url, tmp_path / "local")


def test_a_known_hosts_file_with_the_cli_fetch_off_is_ignored_with_an_error(
    tmp_path, monkeypatch
):
    """Turning the CLI fetch off (to fall back to libgit2, say) must not stop
    every server that also has the known_hosts setting: it is logged and
    ignored, missing file or not."""
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="DEBUG")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    try:
        for path in (tmp_path / "known_hosts", tmp_path / "missing", "known hosts"):
            monkeypatch.setattr(
                opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path)
            )
            validate_git_cli_settings()
            assert known_hosts_file() is None
    finally:
        logger.remove(sink)

    errors = [r for r in records if r["level"].name == "ERROR"]
    assert len(errors) == 3
    assert all("ignored" in r["message"] for r in errors)


def test_the_known_hosts_setting_is_checked_with_the_cli_fetch_on(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    path = tmp_path / "known_hosts"
    path.write_text("")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))
    validate_git_cli_settings()
    spaced = tmp_path / "known hosts"
    spaced.write_text("")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(spaced))
    with pytest.raises(ValueError, match="whitespace"):
        validate_git_cli_settings()
    for unset in (None, ""):
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", unset)
        validate_git_cli_settings()
        assert known_hosts_file() is None


@pytest.mark.parametrize("name", ["100%_hosts", "at-%h", "in-${HOME}", "a$b"])
def test_a_known_hosts_path_that_ssh_would_expand_is_refused(
    name, tmp_path, monkeypatch
):
    """ssh expands % tokens and ${VAR} in UserKnownHostsFile: with OpenSSH
    9.2, ``%_`` fails every op, and ``%h`` or ``${HOME}`` read another file.
    Such a path is refused at startup, as one with whitespace is, and fails
    each SSH op at once, before ssh runs."""
    path = tmp_path / name
    path.write_text("")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))

    with pytest.raises(ValueError, match=r"holds % or \$"):
        validate_git_cli_settings()
    remote = git_cli._remote_for_git("ssh://git@h/r.git", _source("ssh://git@h/r.git"))
    with pytest.raises(GitCliLocalError, match=r"holds % or \$"):
        git_cli._ssh_host_key_options(remote)


@pytest.mark.parametrize("name", ["kn'own", 'kn"own"x', "kn\\own"])
def test_a_known_hosts_path_that_ssh_would_read_as_quoting_is_refused(
    name, tmp_path, monkeypatch
):
    """ssh splits the value of an -o option with quotes and backslashes: with
    OpenSSH 9.2, a ``'`` fails every op (invalid quotes), ``kn"own"x`` reads
    ``knownx`` and ``kn\\own`` reads ``kn\\own`` with one backslash. Such a
    path is refused at startup, and fails each SSH op at once."""
    path = tmp_path / name
    path.write_text("")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))

    with pytest.raises(ValueError, match="a quote or a backslash"):
        validate_git_cli_settings()
    remote = git_cli._remote_for_git("ssh://git@h/r.git", _source("ssh://git@h/r.git"))
    with pytest.raises(GitCliLocalError, match="a quote or a backslash"):
        git_cli._ssh_host_key_options(remote)


@pytest.mark.parametrize("name", ["100%", "in-${HOME}"])
def test_the_server_does_not_start_when_ssh_key_files_would_go_to_a_path_ssh_expands(
    name, tmp_path, monkeypatch
):
    """With no writable /dev/shm, an SSH key file goes to the temp dir, and ssh
    expands % tokens and ${VAR} in its -i path too."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(git_cli, "_SHM", str(tmp_path / "no-shm"))
    temp = tmp_path / name
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))

    with pytest.raises(ValueError, match=r"SSH key files go to .*holds % or \$"):
        validate_git_cli_settings()

    shm = tmp_path / "shm"
    shm.mkdir()
    monkeypatch.setattr(git_cli, "_SHM", str(shm))
    validate_git_cli_settings()


def test_a_relative_known_hosts_path_is_the_server_s_working_directory_s(
    tmp_path, monkeypatch
):
    """Taken at startup, so that ssh, which runs in the clone, reads the file
    the server checked."""
    (tmp_path / "known_hosts").write_text("")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", "known_hosts")

    validate_git_cli_settings()

    assert known_hosts_file() == str(tmp_path / "known_hosts")
    remote = git_cli._remote_for_git("ssh://git@h/r.git", _source("ssh://git@h/r.git"))
    assert f"UserKnownHostsFile={tmp_path / 'known_hosts'}" in (
        git_cli._ssh_host_key_options(remote)
    )


@pytest.mark.parametrize(
    "version, starts",
    [
        ("git version 2.31.8", False),
        ("git version 1.99.0", False),
        ("nonsense", False),
        ("git version 2.32.0", True),
        ("git version 2.39.5 (Apple Git-154)", True),
        ("git version 3.0.0", True),
    ],
)
def test_the_server_does_not_start_with_the_cli_fetch_on_and_a_git_older_than_2_32(
    version, starts, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    _shim(tmp_path, monkeypatch, "git", f"echo '{version}'")
    if starts:
        validate_git_cli_settings()
        return
    with pytest.raises(ValueError, match="needs git 2.32") as info:
        validate_git_cli_settings()
    assert version in str(info.value)


def test_the_server_does_not_start_with_the_cli_fetch_on_and_no_git_or_no_sh(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    not_executable = tmp_path / "sh"
    not_executable.write_text("")
    monkeypatch.setattr(git_cli, "_SH", str(not_executable))
    with pytest.raises(ValueError, match="not executable"):
        validate_git_cli_settings()

    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(ValueError, match="no git on PATH"):
        validate_git_cli_settings()

    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    validate_git_cli_settings()


def test_a_uid_with_no_user_entry_is_logged_as_an_error_that_names_ssh_sources(
    monkeypatch,
):
    """Ssh exits at once under a uid with no passwd entry (an arbitrary uid
    given at runtime, say), where libssh2 needs none.

    The server still starts, as HTTP sources work, but says so once at
    startup.
    """

    def no_entry(uid):
        raise KeyError(f"getpwuid(): uid not found: {uid}")

    errors = []
    sink = logger.add(lambda m: errors.append(m.record["message"]), level="ERROR")
    try:
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
        validate_git_cli_settings()
        with_entry = list(errors)
        monkeypatch.setattr(git_cli.pwd, "getpwuid", no_entry)
        validate_git_cli_settings()
        without_entry = errors[len(with_entry) :]
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
        validate_git_cli_settings()
    finally:
        logger.remove(sink)

    assert with_entry == []
    assert len(without_entry) == 1 and errors == without_entry
    assert f"uid {os.getuid()} has no entry" in without_entry[0]
    assert "over SSH fails" in without_entry[0] and "nss_wrapper" in without_entry[0]


def test_nss_wrapper_s_variables_reach_git_and_no_other_server_variable_does(
    monkeypatch,
):
    """nss_wrapper gives a uid with no passwd entry one, for ssh too, through
    LD_PRELOAD and NSS_WRAPPER_*; nothing else the server has gets through."""
    wrapper = {
        "LD_PRELOAD": "libnss_wrapper.so",
        "NSS_WRAPPER_PASSWD": "/srv/passwd",
        "NSS_WRAPPER_GROUP": "/srv/group",
        "NSS_WRAPPER_HOSTS": "/srv/hosts",
    }
    for key, value in wrapper.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/srv/lib")
    monkeypatch.setenv("OPAL_AUTH_MASTER_TOKEN", "not-for-git")
    url = "ssh://git@127.0.0.1/repo.git"
    source = _source(url, SSHAuthData(username="git", private_key=_FAKE_KEY))

    with git_cli._git_env(source, git_cli._remote_for_git(url, source)) as (env, _):
        given = dict(env)

    assert {k: given.get(k) for k in wrapper} == wrapper
    assert "LD_LIBRARY_PATH" not in given and "OPAL_AUTH_MASTER_TOKEN" not in given


@pytest.mark.parametrize("timeout", [0, -1, float("nan")])
def test_no_fetch_timeout_with_the_cli_fetch_on_is_warned_about(timeout, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", timeout)
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="DEBUG")
    try:
        validate_git_cli_settings()
    finally:
        logger.remove(sink)
    assert [r["level"].name for r in records] == ["WARNING"]
    assert "no time limit" in records[0]["message"]
