"""The scopes fetcher with SCOPES_GIT_FETCH_WITH_CLI on (PER-17993): clones and
fetches run git (``opal_server.git_cli``) under the bookkeeping a libgit2 op
gets (in-flight key, SCOPES_GIT_MAX_WORKERS slot, hung-op marker, metrics,
backoff), and a fetch that hangs no longer keeps its clone from syncing.

Real git against local remotes only (see git_cli_test).
"""

import asyncio
import base64
import errno
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from functools import partial
from pathlib import Path

import httpx
import opal_common.logger as opal_common_logger
import opal_server.scopes.task as task_module
import pygit2
import pytest
from fastapi import FastAPI
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    NoAuthData,
)
from opal_common.schemas.scopes import Scope
from opal_server import git_cli
from opal_server import git_fetcher as git_fetcher_module
from opal_server.config import opal_server_config
from opal_server.git_cli import GitCliError, GitCliTimeoutError, cli_clone, cli_fetch
from opal_server.git_fetcher import (
    GitConcurrencyLimitExceeded,
    GitPolicyFetcher,
    PolicyFetcherCallbacks,
    git_op_in_flight,
    hung_marker_dir,
    run_git_cli_op,
)
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService
from opal_server.tests.git_repack_test import _flock_fails_with

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


class _Recorder(PolicyFetcherCallbacks):
    def __init__(self) -> None:
        self.updates = []

    async def on_update(self, old_head, head):
        self.updates.append((old_head, head))


def _source(url: str, auth=None) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=auth or NoAuthData(auth_type="none"),
    )


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def _fetcher(base: Path, source: GitPolicyScopeSource) -> GitPolicyFetcher:
    return GitPolicyFetcher(base, "scope-1", source, callbacks=_Recorder())


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """Fresh fetcher state per test, and short timeouts."""
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)


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


@pytest.fixture
def cli_on(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics, "increment", lambda m, tags=None: calls.append((m, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda m, v, tags=None: None)
    return calls


def _failures(calls):
    return [
        tags for metric, tags in calls if metric == "opal_server.scopes.git_op_failures"
    ]


def _no_libgit2_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("libgit2 was asked to fetch or clone")

    monkeypatch.setattr(git_fetcher_module, "clone_repository", _boom)
    monkeypatch.setattr(pygit2.remotes.Remote, "fetch", _boom)


async def _clone_at(path: Path, origin_url: str, url: str) -> None:
    """A clone of ``origin_url`` at ``path`` whose remote is ``url``: where a
    fetcher of a source at ``url`` finds its clone."""
    await cli_clone(origin_url, path, _source(origin_url), remote="origin", timeout=60)
    repo = pygit2.Repository(str(path))
    try:
        repo.remotes.set_url("origin", url)
    finally:
        repo.free()


def _ssh_shim(tmp_path: Path, monkeypatch, body: str) -> Path:
    """Put an ``ssh`` that runs ``body`` (sh) first on PATH; the file it
    creates first thing, to tell that it ran."""
    shims = tmp_path / "bin"
    shims.mkdir(exist_ok=True)
    ssh = shims / "ssh"
    started = shims / "ssh.started"
    ssh.write_text(f"#!/bin/sh\n: > '{started}'\n{body}\n")
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    return started


# Long enough for git to have started the ssh shim before it is stopped, even
# on a loaded machine.
_SHIM_TIMEOUT = 1.5


async def _until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition never held"
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_with_the_setting_on_git_clones_and_fetches_and_libgit2_does_not(
    cli_on, git_origin, tmp_path, monkeypatch
):
    _no_libgit2_network(monkeypatch)
    fetcher = _fetcher(tmp_path / "base", _source(git_origin.url))
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "base", _source(git_origin.url))
    first = str(git_origin.repo.references["refs/heads/master"].target)

    await fetcher.fetch_and_notify_on_changes()
    second = git_origin.commit("master", {"policy.rego": "package p\n# two\n"})
    before = (clone / ".git" / "FETCH_HEAD").stat().st_mtime_ns
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetcher.callbacks.updates == [(None, first), (first, second)]
    assert (clone / ".git" / "FETCH_HEAD").stat().st_mtime_ns > before
    assert fetcher.clone_source_id in GitPolicyFetcher.repos_last_fetched
    bundle = fetcher.make_bundle()
    assert bundle.hash == second
    assert "# two" in bundle.policy_modules[0].rego
    assert not git_op_in_flight(fetcher.clone_source_id)


@pytest.mark.parametrize("cli", [True, False], ids=["cli", "libgit2-control"])
@pytest.mark.asyncio
async def test_a_hung_fetch_no_longer_keeps_its_clone_from_syncing(
    cli, git_http, make_origin, tmp_path, monkeypatch, emitted
):
    """The server stalls in the middle of a pack.

    With libgit2 (the control) the fetch's thread is still running after
    its timeout, so the clone is still in flight and the next sync is
    skipped. With git the op is stopped and gone at timeout + grace, and
    once the server recovers the next sync fetches.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    origin = make_origin(git_http.root / "repo.git")
    source = _source(git_http.url("repo.git"))
    fetcher = _fetcher(tmp_path / "base", source)
    await fetcher.fetch_and_notify_on_changes()
    big = origin.commit("master", {"big.bin": os.urandom(2 * 1024 * 1024)})
    git_http.stall_after = 1024
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.5)

    start = time.monotonic()
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    elapsed = time.monotonic() - start

    assert {"op": "fetch", "reason": "timeout"} in _failures(emitted)
    assert (
        GitPolicyFetcher.source_backoff[fetcher.clone_source_id].consecutive_failures
        == 1
    )
    if not cli:
        assert git_op_in_flight(fetcher.clone_source_id)
        return
    assert elapsed <= 0.5 + 0.5 + 1
    assert not git_op_in_flight(fetcher.clone_source_id)
    git_http.stall_after = None
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert fetcher.callbacks.updates[-1][1] == big
    assert fetcher.clone_source_id not in GitPolicyFetcher.source_backoff


@pytest.mark.asyncio
async def test_a_timed_out_cli_fetch_neither_stamps_the_fetch_time_nor_notifies(
    cli_on, git_http, make_origin, tmp_path, monkeypatch
):
    """A fetch stopped at its timeout fetched nothing: the clone's last-fetch
    time stays that of the fetch before (a forced refresh a webhook asks for
    is not taken as done), and no update goes out."""
    origin = make_origin(git_http.root / "repo.git")
    source = _source(git_http.url("repo.git"))
    fetcher = _fetcher(tmp_path / "base", source)
    await fetcher.fetch_and_notify_on_changes()
    fetched = GitPolicyFetcher.repos_last_fetched[fetcher.clone_source_id]
    updates = list(fetcher.callbacks.updates)
    origin.commit("master", {"big.bin": os.urandom(2 * 1024 * 1024)})
    git_http.stall_after = 1024
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.5)

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert git_http.stalled.is_set()
    assert GitPolicyFetcher.repos_last_fetched[fetcher.clone_source_id] == fetched
    assert fetcher.callbacks.updates == updates


@pytest.mark.asyncio
async def test_a_member_that_outlives_sigkill_holds_no_max_workers_slot(
    git_origin, tmp_path, monkeypatch
):
    """SCOPES_GIT_MAX_WORKERS bounds live ops.

    An op that returned at its stop, while a member that outlived
    SIGKILL keeps its clone in flight, no longer counts against it, as a
    lingering libgit2 thread does not.
    """
    started = _ssh_shim(
        tmp_path,
        monkeypatch,
        f'exec "{sys.executable}" -c "import os, time; os.setsid(); time.sleep(4)"',
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 0.3)
    hung, free = tmp_path / "hung", tmp_path / "free"
    await _clone_at(hung, git_origin.url, "ssh://git@127.0.0.1:1/survivor.git")
    await _clone_at(free, git_origin.url, git_origin.url)
    source = _source(git_origin.url)
    survivor = f"survivor-{uuid.uuid4().hex}"

    with pytest.raises(GitCliTimeoutError):
        await run_git_cli_op(
            partial(
                cli_fetch, hung, "origin", source, prune=False, timeout=_SHIM_TIMEOUT
            ),
            timeout=_SHIM_TIMEOUT,
            busy_key=survivor,
        )
    assert started.exists(), "git was stopped before it started ssh"
    new = git_origin.commit("master")
    await asyncio.wait_for(
        run_git_cli_op(
            partial(cli_fetch, free, "origin", source, prune=False, timeout=60),
            timeout=60,
            busy_key=f"free-{uuid.uuid4().hex}",
        ),
        1.5,
    )

    assert git_op_in_flight(survivor)
    assert _refs(free)["refs/remotes/origin/master"] == new
    await _until(lambda: not git_op_in_flight(survivor))


@pytest.mark.asyncio
async def test_stalled_clones_hold_a_healthy_clone_one_fetch_timeout_a_round(
    cli_on, blackhole, git_origin, tmp_path, monkeypatch, processes_with
):
    """Clones of remotes that never answer, begun first, keep a healthy
    source's clone waiting one fetch timeout per round of slots.

    A clone holds its SCOPES_GIT_MAX_WORKERS slot for
    SCOPES_GIT_FETCH_TIMEOUT at most and runs on outside it, to
    SCOPES_GIT_CLONE_TIMEOUT, so a round is not one clone timeout.
    """
    fetch_timeout, clone_timeout = 0.5, 4.0
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 2)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", fetch_timeout)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", clone_timeout)
    marker = f"stalled-{uuid.uuid4().hex}"
    base = tmp_path / "base"
    stalled = [
        _fetcher(base, _source(f"http://127.0.0.1:{blackhole}/{marker}-{i}.git"))
        for i in range(4)
    ]
    syncs = [asyncio.ensure_future(f.fetch_and_notify_on_changes()) for f in stalled]
    await _until(lambda: all(git_op_in_flight(f.clone_source_id) for f in stalled[:2]))
    healthy = _fetcher(base, _source(git_origin.url))
    head = str(git_origin.repo.references["refs/heads/master"].target)

    start = time.monotonic()
    await healthy.fetch_and_notify_on_changes()
    elapsed = time.monotonic() - start

    assert healthy.callbacks.updates == [(None, head)]
    assert elapsed <= 2 * fetch_timeout + 2, (
        f"the healthy clone waited {elapsed:.1f}s for a slot (clone timeout "
        f"{clone_timeout}s, fetch timeout {fetch_timeout}s)"
    )
    assert all(git_op_in_flight(f.clone_source_id) for f in stalled)
    await asyncio.gather(*syncs)
    await _until(lambda: processes_with(marker) == [])


def _stalled_clone(blackhole: int, path: Path, timeout: float, slot_timeout):
    """A clone from a remote that never answers, run by run_git_cli_op as a
    task; the task and the op's in-flight key."""
    key = f"stalled-{uuid.uuid4().hex}"
    url = f"http://127.0.0.1:{blackhole}/{key}.git"
    op = run_git_cli_op(
        partial(cli_clone, url, path, _source(url), remote="origin", timeout=timeout),
        timeout=timeout,
        busy_key=key,
        slot_timeout=slot_timeout,
    )
    return asyncio.ensure_future(op), key


async def _clone_on_a_slot(origin_url: str, path: Path) -> float:
    """How long a git command-line clone of ``origin_url`` took, waiting for
    its SCOPES_GIT_MAX_WORKERS slot included."""
    start = time.monotonic()
    await run_git_cli_op(
        partial(
            cli_clone,
            origin_url,
            path,
            _source(origin_url),
            remote="origin",
            timeout=60,
        ),
        timeout=60,
        busy_key=f"healthy-{uuid.uuid4().hex}",
    )
    return time.monotonic() - start


@pytest.mark.asyncio
async def test_an_op_gives_its_slot_back_at_its_slot_timeout_and_runs_on(
    blackhole, git_origin, tmp_path, monkeypatch, processes_with
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 1)
    slot_timeout, timeout = 0.5, 3.0
    stalled, key = _stalled_clone(
        blackhole, tmp_path / "stalled", timeout, slot_timeout
    )
    await _until(lambda: git_op_in_flight(key))

    waited = await _clone_on_a_slot(git_origin.url, tmp_path / "healthy")

    assert slot_timeout - 0.2 <= waited <= slot_timeout + 1.5
    assert git_op_in_flight(key) and not stalled.done()
    with pytest.raises(GitCliTimeoutError):
        await stalled
    await _until(lambda: not git_op_in_flight(key))
    assert processes_with(key) == []
    # Given back once: the one slot is free, and taking it leaves none.
    slots = git_fetcher_module._get_live_ops_semaphore()
    await asyncio.wait_for(slots.acquire(), 1)
    assert slots.locked()
    slots.release()


@pytest.mark.parametrize("slot_timeout", [None, 0.0, -1.0, math.nan, math.inf])
@pytest.mark.asyncio
async def test_without_a_positive_finite_slot_timeout_an_op_holds_its_slot(
    slot_timeout, blackhole, git_origin, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 1)
    timeout = 1.0
    stalled, key = _stalled_clone(
        blackhole, tmp_path / "stalled", timeout, slot_timeout
    )
    await _until(lambda: git_op_in_flight(key))

    waited = await _clone_on_a_slot(git_origin.url, tmp_path / "healthy")

    assert waited >= timeout - 0.2
    assert stalled.done()
    with pytest.raises(GitCliTimeoutError):
        await stalled


@pytest.mark.asyncio
async def test_a_hung_op_s_marker_is_written_at_its_timeout_and_removed_once_git_is_gone(
    cli_on, git_origin, tmp_path, monkeypatch
):
    """SCOPES_GIT_RECLONE_HUNG_ON_START: the marker says an op is past its
    timeout and not over. Here ssh ignores SIGTERM, so the op stays in its
    kill grace for a second, holding the marker, until SIGKILL ends it."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_RECLONE_HUNG_ON_START", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 1.0)
    started = _ssh_shim(tmp_path, monkeypatch, "trap '' TERM\nexec sleep 30")
    source = _source(f"ssh://git@127.0.0.1:1/hung-{uuid.uuid4().hex}.git")
    base = tmp_path / "base"
    clone = GitPolicyFetcher.repo_clone_path(base, source)
    await _clone_at(clone, git_origin.url, source.url)
    fetcher = _fetcher(base, source)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", _SHIM_TIMEOUT)

    sync = asyncio.ensure_future(fetcher.fetch_and_notify_on_changes(force_fetch=True))
    marked = False
    while not sync.done():
        markers = hung_marker_dir(clone)
        marked = marked or (markers.is_dir() and any(markers.iterdir()))
        await asyncio.sleep(0.02)
    await sync

    assert started.exists(), "git was stopped before it started ssh"
    assert marked
    assert not (
        hung_marker_dir(clone).is_dir() and any(hung_marker_dir(clone).iterdir())
    )
    assert not git_op_in_flight(fetcher.clone_source_id)


@pytest.mark.asyncio
async def test_a_member_that_outlives_sigkill_keeps_its_clone_in_flight_until_it_exits(
    cli_on, git_origin, tmp_path, monkeypatch
):
    """The op returns at timeout + grace + kill wait, but the clone stays in
    flight (later syncs skip it, as for a libgit2 zombie) until the last
    process of the op has exited."""
    started = _ssh_shim(
        tmp_path,
        monkeypatch,
        f'exec "{sys.executable}" -c "import os, time; os.setsid(); time.sleep(4)"',
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 0.3)
    source = _source(f"ssh://git@127.0.0.1:1/survivor-{uuid.uuid4().hex}.git")
    base = tmp_path / "base"
    clone = GitPolicyFetcher.repo_clone_path(base, source)
    await _clone_at(clone, git_origin.url, source.url)
    fetcher = _fetcher(base, source)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", _SHIM_TIMEOUT)

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert started.exists(), "git was stopped before it started ssh"
    assert git_op_in_flight(fetcher.clone_source_id)
    _no_libgit2_network(monkeypatch)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)  # skipped
    await _until(lambda: not git_op_in_flight(fetcher.clone_source_id))


@pytest.mark.asyncio
async def test_a_git_error_is_counted_and_backed_off_as_a_libgit2_one_is(
    cli_on, git_origin, tmp_path, emitted
):
    source = _source(git_origin.url)
    fetcher = _fetcher(tmp_path / "base", source)
    await fetcher.fetch_and_notify_on_changes()
    shutil.move(str(git_origin.path), str(tmp_path / "moved.git"))

    with pytest.raises(GitCliError):
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert _failures(emitted) == [{"op": "fetch", "reason": "git_error"}]
    entry = GitPolicyFetcher.source_backoff[fetcher.clone_source_id]
    assert entry.consecutive_failures == 1 and "GitCliError" in entry.last_error

    missing = _fetcher(tmp_path / "base2", _source(f"file://{tmp_path / 'none.git'}"))
    await missing.fetch_and_notify_on_changes()  # logged, not raised
    assert _failures(emitted)[-1] == {"op": "clone", "reason": "git_error"}
    assert missing.clone_source_id in GitPolicyFetcher.source_backoff


@pytest.mark.asyncio
async def test_a_failed_sync_logs_no_credential(
    cli_on, git_http, make_origin, tmp_path
):
    make_origin(git_http.root / "repo.git")
    token = f"tok{uuid.uuid4().hex}"
    url = git_http.url("repo.git", userinfo=f"alice:pw{token}")
    source = _source(url, GitHubTokenAuthData(token=token))
    git_http.authorization = "Basic bm9ib2R5Om5vdGhpbmc="
    records = []
    sink = logger.add(lambda m: records.append(str(m)), level="DEBUG")
    try:
        await _fetcher(tmp_path / "base", source).fetch_and_notify_on_changes()
    finally:
        logger.remove(sink)

    text = "".join(records)
    assert "Could not clone repo" in text
    assert token not in text


async def _bundles(fetcher: GitPolicyFetcher, base_hash: str):
    return (
        fetcher.make_bundle().model_dump(),
        fetcher.make_bundle(base_hash).model_dump(),
    )


@pytest.mark.asyncio
async def test_switching_the_backend_either_way_keeps_the_clone_and_its_bundles(
    git_origin, tmp_path, monkeypatch
):
    """One clone, synced in turn by libgit2 and git, never cloned again, and
    bundles equal to those of a clone only libgit2 ever fetched.

    The same for a clone made by git and then fetched by libgit2.
    """

    def use_cli(on: bool) -> None:
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", on)

    source = _source(git_origin.url)
    reference = _fetcher(tmp_path / "reference", source)
    switched = _fetcher(tmp_path / "switched", source)
    born_cli = _fetcher(tmp_path / "born-cli", source)
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "switched", source)

    use_cli(False)
    await reference.fetch_and_notify_on_changes()
    await switched.fetch_and_notify_on_changes()
    use_cli(True)
    await born_cli.fetch_and_notify_on_changes()
    inode = clone.stat().st_ino
    first = str(git_origin.repo.references["refs/heads/master"].target)

    for step, backend in enumerate([True, False, True, False]):
        git_origin.commit("master", {f"step{step}.rego": f"package s{step}\n"})
        git_origin.commit("dev")
        use_cli(False)
        await reference.fetch_and_notify_on_changes(force_fetch=True)
        use_cli(backend)
        await switched.fetch_and_notify_on_changes(force_fetch=True)
        use_cli(not backend)
        await born_cli.fetch_and_notify_on_changes(force_fetch=True)

        expected = await _bundles(reference, first)
        assert await _bundles(switched, first) == expected, f"step {step}"
        assert await _bundles(born_cli, first) == expected, f"step {step}"
    assert clone.stat().st_ino == inode
    assert switched.callbacks.updates == reference.callbacks.updates


class _Scopes:
    def __init__(self, scope: Scope) -> None:
        self._scope = scope

    async def get(self, scope_id: str) -> Scope:
        if scope_id != self._scope.scope_id:
            raise ScopeNotFoundError(scope_id)
        return self._scope


class _NoAuth:
    enabled = False

    def __call__(self) -> dict:
        return {}


@pytest.mark.asyncio
async def test_a_bundle_request_during_a_cli_clone_is_held_until_the_clone_lands(
    cli_on, git_origin, tmp_path, monkeypatch
):
    """GET /scopes/:id/policy while git clones the scope's repository, with the
    clone wait's defaults (20 s, no branch refresh interval).

    git clones beside the clone's path and renames the clone into place,
    so that path is not there meanwhile. The request is held, as during
    a libgit2 clone (made in place), and gets the bundle once the clone
    is in place, rather than a 503 at once.
    """
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 20.0)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", 0.0
    )
    source = _source(git_origin.url)
    scope = Scope(scope_id="scope-1", policy=source, data={"entries": []})
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, source)
    shims = tmp_path / "bin"
    shims.mkdir()
    started, gate = shims / "clone.started", shims / "clone.gate"
    (shims / "git").write_text(
        "#!/bin/sh\n"
        f'case " $* " in *" clone "*) : > \'{started}\'; '
        f"while [ ! -e '{gate}' ]; do sleep 0.05; done;; esac\n"
        f'exec \'{shutil.which("git")}\' "$@"\n'
    )
    (shims / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    app = FastAPI()
    app.include_router(
        init_scope_router(
            _Scopes(scope),
            _NoAuth(),
            None,
            ScopesService(
                base_dir=tmp_path, scopes=_Scopes(scope), pubsub_endpoint=None
            ),
        ),
        prefix="/scopes",
    )

    cloning = asyncio.ensure_future(
        cli_clone(git_origin.url, clone, source, remote="origin", timeout=60)
    )
    try:
        await _until(started.exists)
        assert not clone.exists()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            asked = asyncio.ensure_future(client.get("/scopes/scope-1/policy"))
            await asyncio.wait({asked}, timeout=2.5)
            assert not asked.done(), asked.result()
            gate.touch()
            await cloning
            answer = await asyncio.wait_for(asked, 30)
    finally:
        gate.touch()
        await asyncio.wait({cloning}, timeout=30)

    assert answer.status_code == 200, answer.text
    head = str(git_origin.repo.references["refs/heads/master"].target)
    assert answer.json()["hash"] == head


@pytest.mark.asyncio
async def test_scopes_git_fetch_timeout_zero_syncs_with_the_cli(
    cli_on, git_origin, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0)
    fetcher = _fetcher(tmp_path / "base", _source(git_origin.url))
    await fetcher.fetch_and_notify_on_changes()
    new = git_origin.commit("master")
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert fetcher.callbacks.updates[-1][1] == new


@pytest.mark.asyncio
async def test_a_cli_fetch_that_succeeds_clears_the_hung_markers_of_earlier_ops(
    cli_on, git_origin, tmp_path
):
    source = _source(git_origin.url)
    fetcher = _fetcher(tmp_path / "base", source)
    await fetcher.fetch_and_notify_on_changes()
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "base", source)
    markers = hung_marker_dir(clone)
    markers.mkdir(parents=True, exist_ok=True)
    (markers / "otherhost-1-0-deadbeef").touch()
    git_origin.commit("master")

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    await _until(lambda: not markers.exists(), timeout=5)


@pytest.mark.parametrize("prune", [True, False])
@pytest.mark.asyncio
async def test_a_cli_sync_prunes_exactly_when_scopes_git_fetch_prune_is_on(
    prune, cli_on, git_origin, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", prune)
    source = _source(git_origin.url)
    fetcher = _fetcher(tmp_path / "base", source)
    await fetcher.fetch_and_notify_on_changes()
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "base", source)
    git_origin.delete("dev")
    git_origin.commit("master")

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert ("refs/remotes/origin/dev" in _refs(clone)) is (not prune)


@pytest.mark.asyncio
async def test_a_cli_clone_that_times_out_is_counted_as_a_timeout_and_backed_off(
    cli_on, blackhole, tmp_path, monkeypatch, emitted, processes_with
):
    marker = f"hung-{uuid.uuid4().hex}"
    source = _source(f"http://127.0.0.1:{blackhole}/{marker}.git")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.5)
    fetcher = _fetcher(tmp_path / "base", source)
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "base", source)

    await fetcher.fetch_and_notify_on_changes()

    assert _failures(emitted) == [{"op": "clone", "reason": "timeout"}]
    entry = GitPolicyFetcher.source_backoff[fetcher.clone_source_id]
    assert entry.consecutive_failures == 1
    assert "GitCliTimeoutError" in entry.last_error
    assert not clone.exists()
    assert [p.name for p in clone.parent.iterdir() if ".clone-" in p.name] == []
    assert not git_op_in_flight(fetcher.clone_source_id)
    assert processes_with(marker) == []


@pytest.mark.asyncio
async def test_a_cli_op_is_refused_at_the_zombie_cap_before_git_runs(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_ZOMBIES", 1)
    monkeypatch.setattr(git_fetcher_module, "git_busy_count", lambda: 1)
    ran = []

    async def _op(on_gone):
        ran.append(True)

    with pytest.raises(GitConcurrencyLimitExceeded):
        await run_git_cli_op(_op, timeout=5, busy_key="cap-key")
    assert ran == []
    assert not git_op_in_flight("cap-key")


@pytest.mark.parametrize(
    "op, problem",
    [
        ("fetch", "no git"),
        ("fetch", "unreadable known_hosts"),
        ("fetch", "credential in the query"),
        ("fetch", "flock fails"),
        ("clone", "no git"),
        ("clone", "credential in the query"),
        ("clone", "flock fails"),
    ],
)
@pytest.mark.asyncio
async def test_a_failure_on_the_server_s_own_side_is_counted_as_local(
    op, problem, cli_on, git_origin, tmp_path, monkeypatch, emitted
):
    """Nothing the remote did: counted with reason ``local`` and logged at
    ERROR. No backoff (it is for a remote that fails), so the next pass
    tries again, but for a source git cannot be given (here a credential in
    its URL's query string): only a change of the source fixes that, and a
    PUT, which is one, syncs regardless.

    Where the filesystem holding the clones refuses an flock (ENOLCK, as
    NFS without local_lock=flock answers), the fd opened for the clone's
    lock is closed: none is left for the preload to find in the gunicorn
    master.
    """
    url = git_origin.url
    token = f"tok{uuid.uuid4().hex}"
    if problem == "credential in the query":
        url = f"https://127.0.0.1:1/repo.git?access_token={token}"
    elif problem == "unreadable known_hosts":
        url = "ssh://git@127.0.0.1:1/repo.git"
        monkeypatch.setattr(
            opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(tmp_path / "missing")
        )
    source = _source(url)
    base = tmp_path / "base"
    if op == "fetch":
        clone = GitPolicyFetcher.repo_clone_path(base, source)
        await _clone_at(clone, git_origin.url, url)
    if problem == "no git":
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    elif problem == "flock fails":
        _flock_fails_with(monkeypatch, errno.ENOLCK)
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="ERROR")
    fetcher = _fetcher(base, source)
    try:
        for _ in range(2):
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    finally:
        logger.remove(sink)

    assert _failures(emitted) == [{"op": op, "reason": "local"}] * 2
    refused = problem == "credential in the query"
    assert (fetcher.clone_source_id in GitPolicyFetcher.source_backoff) is refused
    assert any("a problem on this server" in r["message"] for r in records)
    assert any("scope-1" in r["message"] for r in records)
    assert not any(token in r["message"] for r in records)
    assert not git_op_in_flight(fetcher.clone_source_id)
    assert git_cli._lock_fds == {}


@pytest.mark.parametrize("cli", [True, False], ids=["cli", "libgit2"])
@pytest.mark.asyncio
async def test_a_source_with_nothing_to_give_a_server_that_asks_is_counted_and_backed_off(
    cli, git_http, make_origin, tmp_path, monkeypatch, emitted
):
    """An http source with no credentials, on a server that asks for some.

    The clone fails as a git error, counted and backed off, with either
    backend.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    make_origin(git_http.root / "repo.git")
    git_http.authorization = _basic("git", "x")
    fetcher = _fetcher(tmp_path / "base", _source(git_http.url("repo.git")))

    await fetcher.fetch_and_notify_on_changes()

    assert _failures(emitted) == [{"op": "clone", "reason": "git_error"}]
    assert fetcher.clone_source_id in GitPolicyFetcher.source_backoff
    assert fetcher.callbacks.updates == []


# server.py's own startup handlers use FastAPI's deprecated on_event; not what
# this test is about.
@pytest.mark.filterwarnings("ignore:\\s*on_event is deprecated:DeprecationWarning")
@pytest.mark.parametrize("readable", [True, False], ids=["readable", "missing"])
def test_with_known_hosts_and_the_cli_off_a_server_starts_only_if_it_can_read_it(
    readable, tmp_path, monkeypatch
):
    """Turning the CLI fetch off keeps a server with a readable
    SCOPES_GIT_SSH_KNOWN_HOSTS starting (libgit2 checks host keys against it
    too); one it cannot read stops the server, as with the CLI fetch on."""
    import opal_server.server as server_module

    monkeypatch.setattr(server_module, "configure_logs", lambda: None)
    path = tmp_path / "known_hosts"
    if readable:
        path.write_text("")
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))

    def _start():
        server_module.OpalServer(
            init_policy_watcher=False, broadcaster_uri=None, enable_jwks_endpoint=False
        )

    if readable:
        _start()
        return
    with pytest.raises(ValueError, match="no readable file"):
        _start()


def test_the_scope_preload_fails_before_any_sync_on_an_unreadable_known_hosts(
    tmp_path, monkeypatch, preload_sandbox, no_redis
):
    events = []

    class _StubService:
        def __init__(self, *args, **kwargs):
            pass

        async def sync_scopes(self, *args, **kwargs):
            events.append("sync_scopes")

    class _StubGitPolicyFetcher:
        @staticmethod
        def reset_caches():
            events.append("reset_caches")

    monkeypatch.setattr(opal_common_logger, "_logs_configured", True)
    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGitPolicyFetcher)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(tmp_path / "missing")
    )
    with pytest.raises(ValueError, match="no readable file"):
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["fetch", "clone"])
async def test_an_op_that_fails_before_it_has_begun_still_leaves_flight(
    op, git_origin, tmp_path
):
    """An op refused before anything runs (a remote name git cannot be given)
    still calls on_gone, or its source would stay in flight, and be skipped,
    for good."""
    key = f"bad-remote-{uuid.uuid4().hex}"
    source = _source(git_origin.url)
    if op == "fetch":
        refused = partial(
            cli_fetch, tmp_path, "--upload-pack=x", source, prune=False, timeout=5
        )
    else:
        refused = partial(
            cli_clone,
            git_origin.url,
            tmp_path / "new",
            source,
            remote="--upload-pack=x",
            timeout=5,
        )
    with pytest.raises(ValueError):
        await run_git_cli_op(refused, timeout=5, busy_key=key)
    assert not git_op_in_flight(key)


# server.py's own startup handlers use FastAPI's deprecated on_event; not what
# this test is about.
@pytest.mark.filterwarnings("ignore:\\s*on_event is deprecated:DeprecationWarning")
def test_a_worker_s_start_removes_the_ssh_key_files_of_processes_that_died(
    tmp_path, monkeypatch
):
    import opal_server.server as server_module

    monkeypatch.setattr(server_module, "configure_logs", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    shm = tmp_path / "shm"
    shm.mkdir()
    monkeypatch.setattr(git_cli, "_SHM", str(shm))
    dead = subprocess.Popen(["true"])
    dead.wait()
    left = shm / f"opal-git-ssh-{dead.pid}-x1"
    left.mkdir()
    (left / "id").write_text("key")
    live, live_lock = git_cli._make_key_dir()

    try:
        server_module.OpalServer(
            init_policy_watcher=False, broadcaster_uri=None, enable_jwks_endpoint=False
        )
    finally:
        os.close(live_lock)

    assert not left.exists()
    assert Path(live).exists()


@pytest.mark.asyncio
async def test_a_fetch_whose_fetch_head_cannot_be_written_still_counts_as_one(
    cli_on, git_origin, tmp_path, monkeypatch
):
    """A fetch whose FETCH_HEAD cannot be rewritten (a full disk, say) did
    fetch: the scope is updated and the fetch recorded, and the ERROR names
    FETCH_HEAD. What reads FETCH_HEAD's age notices a disk that stays full."""
    source = _source(git_origin.url)
    fetcher = _fetcher(tmp_path / "base", source)
    await fetcher.fetch_and_notify_on_changes()
    before = GitPolicyFetcher.repos_last_fetched[fetcher.clone_source_id]
    new = git_origin.commit("master", {"policy.rego": "package p\n# two\n"})
    real_write = Path.write_bytes

    def _full(path, data):
        if path.name == "FETCH_HEAD":
            raise OSError(28, "No space left on device")
        return real_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", _full)
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="ERROR")
    try:
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    finally:
        logger.remove(sink)

    assert fetcher.callbacks.updates[-1][1] == new
    assert GitPolicyFetcher.repos_last_fetched[fetcher.clone_source_id] > before
    assert fetcher.clone_source_id not in GitPolicyFetcher.source_backoff
    assert [r["message"] for r in records if "FETCH_HEAD" in r["message"]]
