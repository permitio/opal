"""The INFO lines of the scope git changes, kept until 0.10 runs in production.

One line per event, never per request: the settings at the pre-fork
preload, the preload's time and the close of its Redis client, each
fetch a sync pass makes, and each stop of a git that ran past its time.
A source's URL appears only redacted.
"""

import datetime
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import opal_common.logger as opal_common_logger
import opal_server.scopes.task as task_module
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.log_capture import capture_records
from opal_server import git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
_TOKEN = "s3cr3t-token-value"


class _Scopes:
    def __init__(self, scopes):
        self.scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]

    async def all(self):
        return list(self.scopes.values())


class _PubSub:
    async def publish(self, topics, data=None):
        pass


def _scope(scope_id: str, url: str, branch: str) -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch=branch, auth=NoAuthData()
        ),
    )


def _info(logs, starting_with: str) -> list:
    return [
        r["message"]
        for r in logs.emitted
        if r["level"].name == "INFO" and r["message"].startswith(starting_with)
    ]


@pytest.fixture(autouse=True)
def _fresh_fetcher_state(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 0)
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()


# --- each fetch of a sync pass -------------------------------------------------


async def _pass_over(base_dir: Path, url: str, branches: list, waiting=None):
    """A clone of ``url`` made by one scope's sync, a fetch by its refresh,
    then a sync pass over a scope on each of ``branches``, with ``waiting``
    (branch -> syncs) in the clone's batch when it starts; what they logged."""
    scopes = [_scope(f"s-{i}", url, b) for i, b in enumerate(branches)]
    svc = ScopesService(
        base_dir=base_dir, scopes=_Scopes(scopes), pubsub_endpoint=_PubSub()
    )
    with capture_records() as logs:
        await svc.sync_scope(scope_id="s-0")
        await svc.sync_scope(scope_id="s-0", force_fetch=True)
        if waiting:
            source_id = GitPolicyFetcher.source_id(scopes[0].policy)
            GitPolicyFetcher.pending_branches[source_id] = dict(waiting)
        await svc.sync_scopes(run_due_repacks=False)
    return logs


@_needs_git
@pytest.mark.asyncio
@pytest.mark.fetch_backend("cli")
async def test_a_pass_fetch_logs_its_source_and_the_branches_it_asks_for(
    git_http, make_origin, tmp_path
):
    """With a token in the source URL: one line for the clone's one fetch of
    the pass, naming the source redacted and the two branches by name, and
    none for the clone or the refresh's fetch before the pass.

    Mutation: logging the URL as given puts the token in the line; logging
    every sync's fetch logs two lines.
    """
    make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git").replace("http://", f"http://oauth2:{_TOKEN}@")
    base_dir = tmp_path / "base"
    source_id = GitPolicyFetcher.source_id(_scope("s", url, "master").policy)

    logs = await _pass_over(base_dir, url, ["master", "dev"])

    redacted = url.replace(f"oauth2:{_TOKEN}@", "***@")
    assert _info(logs, "Sync pass fetching") == [
        f"Sync pass fetching {redacted} ({source_id}): 2 branches by name, with 0 "
        "syncs from the clone's batch"
    ]
    assert not [r for r in logs.emitted if _TOKEN in r["message"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backend, most, asked",
    [
        ("libgit2", 1000, "every branch (libgit2)"),
        (
            "cli",
            0,
            "every branch (OPAL_SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES=0)",
        ),
        (
            "cli",
            1,
            "every branch (2 tracked, OPAL_SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES=1)",
        ),
    ],
    ids=["libgit2", "cli-narrow-off", "cli-over-the-cap"],
)
async def test_a_pass_fetch_of_every_branch_says_why(
    git_origin, tmp_path, monkeypatch, backend, most, asked
):
    if backend == "cli" and shutil.which("git") is None:
        pytest.skip("needs git")
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", backend == "cli"
    )
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", most
    )
    source_id = GitPolicyFetcher.source_id(_scope("s", git_origin.url, "master").policy)

    logs = await _pass_over(tmp_path / "base", git_origin.url, ["master", "dev"])

    assert _info(logs, "Sync pass fetching") == [
        f"Sync pass fetching {git_origin.url} ({source_id}): {asked}, with 0 "
        "syncs from the clone's batch"
    ]


@_needs_git
@pytest.mark.asyncio
@pytest.mark.fetch_backend("cli")
async def test_a_pass_fetch_counts_the_syncs_of_the_batch_it_takes(
    git_origin, tmp_path
):
    """Three refreshes waiting for the clone, two of them on one branch: the
    pass's fetch names three syncs.

    Mutation: counting the batch's branches says two.
    """
    source_id = GitPolicyFetcher.source_id(_scope("s", git_origin.url, "master").policy)

    logs = await _pass_over(
        tmp_path / "base", git_origin.url, ["master"], waiting={"dev": 2, "master": 1}
    )

    assert _info(logs, "Sync pass fetching") == [
        f"Sync pass fetching {git_origin.url} ({source_id}): 2 branches by name, "
        "with 3 syncs from the clone's batch"
    ]


@_needs_git
@pytest.mark.asyncio
@pytest.mark.fetch_backend("cli")
async def test_a_pass_fetch_with_no_branch_that_can_be_a_ref_says_so(
    git_origin, tmp_path
):
    """Every scope of the clone on a branch that cannot be a ref: the pass
    fetches every branch, and the line does not blame the cap.

    Mutation: counting the names before the ref check reads "2 tracked".
    """
    source_id = GitPolicyFetcher.source_id(_scope("s", git_origin.url, "x~1").policy)

    logs = await _pass_over(tmp_path / "base", git_origin.url, ["x~1", "y~2"])

    assert _info(logs, "Sync pass fetching") == [
        f"Sync pass fetching {git_origin.url} ({source_id}): every branch (no "
        "tracked branch can be a ref), with 0 syncs from the clone's batch"
    ]


# --- each fetch for a client with no policy ---------------------------------------


@_needs_git
@pytest.mark.asyncio
@pytest.mark.fetch_backend("cli")
async def test_a_cold_start_fetch_logs_its_source_once(git_http, make_origin, tmp_path):
    """The sync of a client with no policy (fresh_within): one line when it
    fetches, naming the source redacted, and none when a fetch of the branch
    that started after it was asked for stands in for it, nor for the clone or
    a plain refresh.

    Mutation: logging only the fetches of a pass logs none for it.
    """
    make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git").replace("http://", f"http://oauth2:{_TOKEN}@")
    scope = _scope("s-0", url, "master")
    source_id = GitPolicyFetcher.source_id(scope.policy)
    svc = ScopesService(
        base_dir=tmp_path / "base", scopes=_Scopes([scope]), pubsub_endpoint=_PubSub()
    )

    with capture_records() as logs:
        await svc.sync_scope(scope_id="s-0")
        asked = datetime.datetime.now()
        await svc.sync_scope(scope_id="s-0", force_fetch=True)
        await svc.sync_scope(
            scope_id="s-0", force_fetch=True, req_time=asked, fresh_within=55.0
        )
        await svc.sync_scope(scope_id="s-0", force_fetch=True, fresh_within=0.01)

    redacted = url.replace(f"oauth2:{_TOKEN}@", "***@")
    assert _info(logs, "Cold-start fetching") == [
        f"Cold-start fetching {redacted} ({source_id}) for a client with no "
        "policy: 1 branches by name, with 1 syncs from the clone's batch"
    ]
    assert _info(logs, "Sync pass fetching") == []
    assert not [r for r in logs.emitted if _TOKEN in r["message"]]


# --- the settings, the preload's time and its Redis client -----------------------


@pytest.fixture
def preload(monkeypatch, preload_sandbox, no_redis):
    """preload_scopes() with no scopes, logging already configured (as
    scripts/gunicorn_conf.py leaves it), and SCOPES on."""
    monkeypatch.setattr(opal_common_logger, "_logs_configured", True)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    return task_module.ScopesPolicyWatcherTask.preload_scopes


@pytest.mark.parametrize(
    "cli, known_hosts, line",
    [
        (
            True,
            None,
            "Scope git settings: git command-line fetches, fetch timeout 60s, "
            "clone timeout 900s, kill grace 7s, a fetch asks for up to 250 branches "
            "by name, one clone per repository, SSH host keys trusted on first use",
        ),
        (
            False,
            "known",
            "Scope git settings: libgit2 fetches, fetch and clone timeout 60s, 3 "
            "clones per repository, SSH host keys checked against {known}",
        ),
    ],
    ids=["cli", "libgit2-strict"],
)
def test_the_preload_logs_the_scope_git_settings_once(
    preload, monkeypatch, tmp_path, cli, known_hosts, line
):
    known = tmp_path / "known_hosts"
    known.write_text("")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    monkeypatch.setattr(
        opal_server_config,
        "SCOPES_GIT_SSH_KNOWN_HOSTS",
        str(known) if known_hosts else None,
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 900.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 7.0)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 250
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    if cli and shutil.which("git") is None:
        pytest.skip("needs git")

    with capture_records() as logs:
        preload()

    assert _info(logs, "Scope git settings") == [line.format(known=known)]


def test_with_narrow_fetches_off_the_settings_line_says_every_branch(
    preload, monkeypatch
):
    if shutil.which("git") is None:
        pytest.skip("needs git")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 0
    )

    with capture_records() as logs:
        preload()

    [line] = _info(logs, "Scope git settings")
    assert "a fetch asks for every branch (narrow off)" in line


def test_a_timeout_of_0_reads_none_in_the_settings_line(preload, monkeypatch):
    """0 is no limit for SCOPES_GIT_FETCH_TIMEOUT and so for the clone timeout
    it defaults from."""
    if shutil.which("git") is None:
        pytest.skip("needs git")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", None)

    with capture_records() as logs:
        preload()

    [line] = _info(logs, "Scope git settings")
    assert "fetch timeout none, clone timeout none," in line


def test_the_preload_logs_its_time_and_the_close_of_its_redis_client(preload):
    """In this order: the close, before the fork; then the time from the
    preload's start to the fork, the sync's share included."""
    with capture_records() as logs:
        preload()

    lines = [
        r["message"]
        for r in logs.emitted
        if r["level"].name == "INFO"
        and r["message"].startswith(("Preload:", "Preload took"))
    ]
    assert len(lines) == 2, lines
    assert lines[0] == "Preload: closed its Redis client, before the workers are forked"
    assert lines[1].startswith("Preload took ")
    assert lines[1].endswith("s of it in the scopes' sync")


def test_a_failed_redis_close_is_not_logged_as_closed(preload, monkeypatch):
    class _CloseFails:
        def __init__(self, url):
            pass

        async def close(self):
            raise ConnectionError("Timed out closing connection")

    monkeypatch.setattr(task_module, "RedisDB", _CloseFails)

    with capture_records() as logs:
        preload()

    assert _info(logs, "Preload: closed") == []
    assert len(_info(logs, "Preload took ")) == 1


# --- the stop of a git that ran past its time ------------------------------------


@_needs_git
@pytest.mark.asyncio
@pytest.mark.fetch_backend("cli")
@pytest.mark.parametrize(
    "grace, how",
    [(5.0, "): SIGTERM was enough"), (0.0, ") with SIGKILL")],
    ids=["sigterm", "sigkill"],
)
async def test_a_stopped_git_command_line_op_logs_how_it_was_stopped(
    blackhole, tmp_path, monkeypatch, grace, how
):
    """A clone of a remote that never answers, stopped at its timeout: git
    exits on SIGTERM; with no kill grace it gets SIGKILL at once. The line
    names the op and its clone, never the URL (a token in it here).

    Mutation: dropping the line on either stop path.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", grace)
    url = f"http://oauth2:{_TOKEN}@127.0.0.1:{blackhole}/repo.git"
    scope = _scope("s-0", url, "master")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "base", scope.policy)
    svc = ScopesService(
        base_dir=tmp_path / "base", scopes=_Scopes([scope]), pubsub_endpoint=_PubSub()
    )

    with capture_records() as logs:
        await svc.sync_scope(scope_id="s-0")

    [line] = _info(logs, "Stopped git")
    assert line.startswith(f"Stopped git clone into {clone} (pid ")
    assert line.endswith(how)
    assert not [r for r in logs.emitted if _TOKEN in r["message"]]


def _group(tmp_path: Path, ignore_term: bool) -> subprocess.Popen:
    ready = tmp_path / "ready"
    trap = 'trap "" TERM; ' if ignore_term else ""
    proc = subprocess.Popen(
        ["/bin/sh", "-c", f'{trap}: > "$1"; /bin/sleep 30', "sh", str(ready)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not ready.exists():
        assert time.monotonic() < deadline, "the command never ran"
        time.sleep(0.01)
    return proc


@pytest.mark.skipif(sys.platform == "win32", reason="process groups")
@pytest.mark.parametrize(
    "ignore_term, how",
    [(False, ": SIGTERM was enough"), (True, " with SIGKILL")],
    ids=["sigterm", "sigkill"],
)
def test_a_stopped_repack_git_logs_how_it_was_stopped(tmp_path, ignore_term, how):
    proc = _group(tmp_path, ignore_term)
    try:
        with capture_records() as logs:
            assert git_fetcher._stop_repack(proc, 0.3, "git repack in /clones/x")
    finally:
        if proc.returncode is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()

    assert _info(logs, "Stopped") == [
        f"Stopped git repack in /clones/x (pid {proc.pid}){how}"
    ]
