"""The git command line is the default scope fetch backend: with it each
repository has one clone, and a clone gets a timeout of its own.

libgit2 stays the second backend (OPAL_SCOPES_GIT_FETCH_WITH_CLI=false), with
its SCOPES_REPO_CLONES_SHARDS clones per repository.
"""

import hashlib
import os
import shutil
from pathlib import Path

import pygit2
import pytest
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server import git_cli
from opal_server import git_fetcher as git_fetcher_module
from opal_server.config import OpalServerConfig, opal_server_config
from opal_server.git_cli import clone_timeout, validate_git_cli_settings
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    PolicyFetcherCallbacks,
    clone_shards,
)
from opal_server.tests.conftest import fetch_backend_cli_setting

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


class _Recorder(PolicyFetcherCallbacks):
    def __init__(self) -> None:
        self.updates = []

    async def on_update(self, old_head, head):
        self.updates.append((old_head, head))


def _source(url: str, branch: str = "master") -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git", url=url, branch=branch, auth=NoAuthData(auth_type="none")
    )


def _shard(branch: str) -> str:
    return GitPolicyFetcher.source_id(_source("https://h.example/r.git", branch))[-1]


def _branch_on_shard(index: int, shards: int) -> str:
    """A branch name libgit2 maps to clone ``index`` of ``shards``."""
    i = 0
    while hashlib.sha256(f"env-{i}".encode()).digest()[0] % shards != index:
        i += 1
    return f"env-{i}"


def _remote_ref(clone: Path, branch: str) -> str:
    repo = pygit2.Repository(str(clone))
    try:
        return str(repo.references[f"refs/remotes/origin/{branch}"].target)
    finally:
        repo.free()


def _clone_dirs(base: Path):
    return sorted(
        p.name
        for p in GitPolicyFetcher.base_dir(base).iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


async def _sync(base: Path, source: GitPolicyScopeSource, scope_id: str = "scope-1"):
    fetcher = GitPolicyFetcher(base, scope_id, source, callbacks=_Recorder())
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    return fetcher


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """Fresh fetcher state, scopes on, the shards warning not given yet in this
    process, and the documented defaults for what these tests read."""
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(git_cli, "_shards_warned_pids", set())
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 120.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)


@pytest.fixture
def log_lines():
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="DEBUG")

    def _lines(level: str):
        return [r["message"] for r in records if r["level"].name == level]

    yield _lines
    logger.remove(sink)


def _unset_config() -> OpalServerConfig:
    """A server config read from an environment that sets none of its keys."""
    return OpalServerConfig(prefix="OPAL_UNSET_FOR_DEFAULTS_")


def test_the_git_cli_is_the_default_backend_with_one_clone_per_repository():
    config = _unset_config()
    assert config.SCOPES_GIT_FETCH_WITH_CLI is True
    assert config.SCOPES_REPO_CLONES_SHARDS == 1
    assert config.SCOPES_GIT_CLONE_TIMEOUT is None


@pytest.mark.parametrize("shards", [1, 3, 7])
def test_with_the_cli_every_branch_maps_to_clone_0(shards, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", shards)
    assert clone_shards() == 1
    assert {_shard(f"b{i}") for i in range(64)} == {"0"}


def test_libgit2_keeps_its_shards(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    assert clone_shards() == 3
    assert {_shard(f"b{i}") for i in range(64)} == {"0", "1", "2"}


def test_shards_other_than_1_with_the_cli_warn_once_per_process(monkeypatch, log_lines):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)

    validate_git_cli_settings()
    validate_git_cli_settings()

    warned = [m for m in log_lines("WARNING") if "SCOPES_REPO_CLONES_SHARDS=3" in m]
    assert len(warned) == 1
    assert "is ignored with the git command-line fetch" in warned[0]
    assert "OPAL_SCOPES_GIT_FETCH_WITH_CLI=false" in warned[0]


def test_a_worker_forked_after_the_warning_gives_its_own(monkeypatch, log_lines):
    """The master's preload warns, and so does each worker it forks, which
    inherits what the master recorded."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    validate_git_cli_settings()
    master = os.getpid()
    monkeypatch.setattr(git_cli.os, "getpid", lambda: master + 1)

    validate_git_cli_settings()
    validate_git_cli_settings()

    assert len([m for m in log_lines("WARNING") if "SHARDS=3" in m]) == 2


@pytest.mark.parametrize("cli, shards", [(True, 1), (False, 3)])
def test_no_shards_warning_with_one_shard_or_with_libgit2(
    cli, shards, monkeypatch, log_lines
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", shards)
    validate_git_cli_settings()
    assert not [m for m in log_lines("WARNING") if "SCOPES_REPO_CLONES_SHARDS" in m]


@pytest.mark.parametrize("cli", [True, False], ids=["cli", "libgit2"])
@pytest.mark.parametrize("shards", [0, -1])
def test_a_shard_count_below_1_stops_the_server(cli, shards, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", shards)
    with pytest.raises(ValueError, match=f"SCOPES_REPO_CLONES_SHARDS={shards}"):
        validate_git_cli_settings()


def test_a_shard_count_that_is_not_a_number_stops_the_server(monkeypatch):
    monkeypatch.setenv("OPAL_SHARDS_TEST_SCOPES_REPO_CLONES_SHARDS", "abc")
    with pytest.raises(ValueError):
        OpalServerConfig(prefix="OPAL_SHARDS_TEST_")


@pytest.mark.parametrize("cli", [True, False], ids=["cli", "libgit2"])
def test_without_scopes_nothing_is_checked_and_no_git_is_needed(
    cli, monkeypatch, tmp_path, log_lines
):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 0)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(tmp_path / "missing")
    )
    monkeypatch.setenv("PATH", str(tmp_path))

    validate_git_cli_settings()

    assert log_lines("WARNING") == [] and log_lines("ERROR") == []


@pytest.mark.parametrize(
    "git, error",
    [(None, "no git on PATH"), ("echo 'git version 2.31.0'", "needs git 2.32")],
    ids=["no-git", "old-git"],
)
def test_scopes_without_a_usable_git_names_the_libgit2_way_back(
    git, error, monkeypatch, tmp_path
):
    shims = tmp_path / "bin"
    shims.mkdir()
    if git is not None:
        (shims / "git").write_text(f"#!/bin/sh\n{git}\n")
        (shims / "git").chmod(0o755)
    monkeypatch.setenv("PATH", str(shims))
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)

    with pytest.raises(ValueError, match=error) as info:
        validate_git_cli_settings()

    assert "OPAL_SCOPES_GIT_FETCH_WITH_CLI=false" in str(info.value)


# server.py's own startup handlers use FastAPI's deprecated on_event; not what
# this test is about.
@pytest.mark.filterwarnings("ignore:\\s*on_event is deprecated:DeprecationWarning")
@pytest.mark.parametrize("scopes", [False, True], ids=["no-scopes", "scopes"])
def test_a_server_checks_and_cleans_up_for_the_git_cli_only_in_scopes_mode(
    scopes, monkeypatch, tmp_path
):
    import opal_server.server as server_module

    monkeypatch.setattr(server_module, "configure_logs", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", scopes)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    swept = []
    monkeypatch.setattr(server_module, "remove_dead_key_dirs", lambda: swept.append(1))
    monkeypatch.setenv("PATH", str(tmp_path))

    def _start():
        server_module.OpalServer(
            init_policy_watcher=False, broadcaster_uri=None, enable_jwks_endpoint=False
        )

    if scopes:
        with pytest.raises(ValueError, match="no git on PATH"):
            _start()
    else:
        _start()
    assert swept == []


def test_the_clone_timeout_defaults_to_5_times_the_fetch_timeout(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    assert clone_timeout() == 300.0
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0)
    assert clone_timeout() == 0
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 90.0)
    assert clone_timeout() == 90.0


@pytest.mark.parametrize(
    "fetch, clone, starts",
    [
        (60.0, 59.0, False),
        (60.0, 60.0, True),
        (60.0, 0.0, True),
        (0.0, 600.0, False),
        (0.0, 0.0, True),
    ],
)
def test_a_clone_timeout_below_the_fetch_timeout_stops_the_server(
    fetch, clone, starts, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", fetch)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", clone)
    if starts:
        validate_git_cli_settings()
        return
    with pytest.raises(ValueError, match="SCOPES_GIT_CLONE_TIMEOUT"):
        validate_git_cli_settings()


def test_libgit2_ignores_the_clone_timeout(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 1.0)
    validate_git_cli_settings()


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


@_needs_git
@pytest.mark.asyncio
async def test_with_no_fetch_setting_scopes_are_cloned_and_fetched_by_git(
    git_http, make_origin, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config,
        "SCOPES_GIT_FETCH_WITH_CLI",
        _unset_config().SCOPES_GIT_FETCH_WITH_CLI,
    )
    origin = make_origin(git_http.root / "repo.git")
    source = _source(git_http.url("repo.git"))
    await _sync(tmp_path / "base", source)
    head = origin.commit("master")

    fetcher = await _sync(tmp_path / "base", source)

    assert fetcher.callbacks.updates[-1][1] == head
    agents = {headers.get("User-Agent", "") for _, _, headers in git_http.requests}
    assert agents and all(a.startswith("git/") for a in agents), agents
    assert not any("libgit2" in a for a in agents), agents
    protocols = {headers.get("Git-Protocol") for _, _, headers in git_http.requests}
    assert protocols == {"version=2"}


@_needs_git
@pytest.mark.asyncio
async def test_with_the_cli_and_3_shards_set_one_repository_has_one_clone(
    git_origin, tmp_path, monkeypatch, log_lines
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    validate_git_cli_settings()
    branches = [_branch_on_shard(i, 3) for i in range(3)]
    heads = {}
    for branch in branches:
        git_origin.branch(branch)
        heads[branch] = git_origin.commit(branch)
    base = tmp_path / "base"

    served = {}
    for i, branch in enumerate(branches):
        fetcher = await _sync(base, _source(git_origin.url, branch), f"scope-{i}")
        served[branch] = fetcher.callbacks.updates[-1][1]

    assert served == heads
    clones = _clone_dirs(base)
    assert clones == [GitPolicyFetcher.source_id(_source(git_origin.url))]
    assert clones[0].endswith("-0")
    assert len([m for m in log_lines("WARNING") if "SHARDS=3" in m]) == 1


@_needs_git
@pytest.mark.asyncio
async def test_libgit2_with_3_shards_clones_a_repository_once_per_shard(
    git_origin, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    base = tmp_path / "base"
    for i in range(3):
        branch = _branch_on_shard(i, 3)
        git_origin.branch(branch)
        await _sync(base, _source(git_origin.url, branch), f"scope-{i}")

    clones = _clone_dirs(base)
    assert [name[-2:] for name in clones] == ["-0", "-1", "-2"]


@_needs_git
@pytest.mark.asyncio
async def test_a_libgit2_shard_0_clone_is_fetched_by_the_cli_without_a_new_clone(
    git_origin, tmp_path, monkeypatch
):
    """A server switched to the git command line on a volume that holds
    libgit2's shard clones (a restart in place) fetches shard 0 for every
    scope, and leaves the other shards alone."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    on_0, on_1 = _branch_on_shard(0, 3), _branch_on_shard(1, 3)
    base = tmp_path / "base"
    for branch in (on_0, on_1):
        git_origin.branch(branch)
        await _sync(base, _source(git_origin.url, branch), branch)
    clone_0 = GitPolicyFetcher.repo_clone_path(base, _source(git_origin.url, on_0))
    clone_1 = GitPolicyFetcher.repo_clone_path(base, _source(git_origin.url, on_1))
    assert clone_0 != clone_1
    old_on_1 = _remote_ref(clone_1, on_1)
    new_on_1 = git_origin.commit(on_1)
    for name in ("repos", "repos_last_fetched", "repo_locks"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    cloned = []

    async def _no_clone(*args, **kwargs):
        cloned.append(args)
        raise AssertionError("the git command line was asked to clone")

    monkeypatch.setattr(git_fetcher_module, "cli_clone", _no_clone)

    fetcher = await _sync(base, _source(git_origin.url, on_1), on_1)

    assert cloned == []
    assert fetcher.callbacks.updates == [(None, new_on_1)]
    assert _remote_ref(clone_0, on_1) == new_on_1
    assert _remote_ref(clone_1, on_1) == old_on_1


@_needs_git
@pytest.mark.parametrize(
    "clone_setting, lands", [(None, True), (1.0, False)], ids=["default", "1s"]
)
@pytest.mark.asyncio
async def test_a_clone_slower_than_the_fetch_timeout_lands_within_the_clone_timeout(
    clone_setting, lands, git_http, make_origin, tmp_path, monkeypatch, emitted
):
    """The server holds each pack 2 seconds; the fetch timeout is 1.

    A clone gets the clone timeout (by default 5 times the fetch timeout)
    and lands; a fetch keeps the fetch timeout. The control sets the clone
    timeout to the fetch timeout: the clone is stopped.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 1.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", clone_setting)
    origin = make_origin(git_http.root / "repo.git")
    head = str(origin.repo.references["refs/heads/master"].target)
    source = _source(git_http.url("repo.git"))
    git_http.delay = 2.0

    fetcher = await _sync(tmp_path / "base", source)

    if not lands:
        assert _failures(emitted) == [{"op": "clone", "reason": "timeout"}]
        assert fetcher.callbacks.updates == []
        return
    assert _failures(emitted) == []
    assert fetcher.callbacks.updates == [(None, head)]
    origin.commit("master")
    await _sync(tmp_path / "base", source)
    assert _failures(emitted) == [{"op": "fetch", "reason": "timeout"}]


@pytest.mark.fetch_backend("both")
def test_the_fetch_backend_marker_runs_a_test_once_per_backend(fetch_backend):
    assert fetch_backend in ("cli", "libgit2")
    assert opal_server_config.SCOPES_GIT_FETCH_WITH_CLI is (fetch_backend == "cli")
    assert clone_shards() == 1 or fetch_backend == "libgit2"


@pytest.mark.fetch_backend("libgit2")
def test_the_fetch_backend_marker_pins_one_backend(fetch_backend):
    assert fetch_backend == "libgit2"
    assert opal_server_config.SCOPES_GIT_FETCH_WITH_CLI is False


@pytest.mark.parametrize("name", [None, "", "git", "both"])
def test_a_fetch_backend_marker_without_a_backend_s_name_is_refused(name):
    with pytest.raises(ValueError, match="fetch_backend"):
        fetch_backend_cli_setting(name)
