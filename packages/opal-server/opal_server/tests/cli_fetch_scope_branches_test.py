"""SCOPES_GIT_FETCH_SCOPE_BRANCHES: with the CLI backend, a fetch asks only
for the branches the scope store's scopes track on that clone (PER-17998).

Real fetches against local origins with the real git; the scope store is an
in-memory fake.
"""

import datetime
import subprocess
from pathlib import Path

import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server import git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    FETCH_BACKEND_CLI,
    FETCH_BACKEND_PYGIT2,
    GitPolicyFetcher,
    _cli_fetch,
    _cli_fetch_argv,
)
from opal_server.scopes import service as service_module
from opal_server.scopes.service import ScopesService


def _git(*args):
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    _git("init", "-q", "-b", "main", str(origin))
    _git("-C", str(origin), "config", "user.email", "t@example.com")
    _git("-C", str(origin), "config", "user.name", "t")
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "c1")
    return origin


def _remote_refs(clone: Path) -> set:
    out = _git("-C", str(clone), "for-each-ref", "--format=%(refname)", "refs/remotes")
    return set(out.splitlines())


def _head(repo: Path, ref: str) -> str:
    return _git("-C", str(repo), "rev-parse", ref)


@pytest.fixture(autouse=True)
def clear_fetcher_caches(monkeypatch):
    def clear():
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repo_locks.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.repos_last_fetched_branches.clear()
        GitPolicyFetcher.source_backoff.clear()
        GitPolicyFetcher.source_branches = {}
        GitPolicyFetcher.source_branches_read_at = None

    clear()
    yield
    clear()


@pytest.fixture
def narrow(monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_BACKEND", FETCH_BACKEND_CLI
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_SCOPE_BRANCHES", True)


def _source(origin: Path, branch: str) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git",
        url=str(origin),
        branch=branch,
        auth=NoAuthData(auth_type="none"),
    )


def _sid(origin: Path, branch: str = "main") -> str:
    return GitPolicyFetcher.source_id(_source(origin, branch))


async def _cloned(tmp_path, origin):
    """A clone made by a scope on main; returns (base dir, clone path)."""
    base = tmp_path / "base"
    await GitPolicyFetcher(
        base, "s-main", _source(origin, "main")
    ).fetch_and_notify_on_changes()
    return base, Path(GitPolicyFetcher.repo_clone_path(base, _source(origin, "main")))


class FakeScopes:
    def __init__(self, scopes):
        self.scopes = {s.scope_id: s for s in scopes}
        self.reads = 0

    async def get(self, scope_id):
        return self.scopes[scope_id]

    async def all(self):
        self.reads += 1
        return list(self.scopes.values())


class NoPubSub:
    async def publish(self, topics, data=None):
        pass


# --- what is asked for ---------------------------------------------------------


def test_the_setting_is_off_by_default():
    assert opal_server_config.SCOPES_GIT_FETCH_SCOPE_BRANCHES is False


def test_refspecs_on_stdin_bring_a_negotiation_tip_and_the_skipping_negotiator():
    argv = _cli_fetch_argv("/git", "/clone", "origin", False, stdin=True)
    assert argv[-3:] == ["--negotiation-tip=refs/heads/scopes/*", "--stdin", "origin"]
    assert argv[argv.index("fetch.negotiationAlgorithm=skipping") - 1] == "-c"
    assert argv.index("fetch.negotiationAlgorithm=skipping") < argv.index("fetch")
    plain = _cli_fetch_argv("/git", "/clone", "origin", False)
    assert "--stdin" not in plain
    assert "fetch.negotiationAlgorithm=skipping" not in plain
    assert not any(a.startswith("--negotiation-tip") for a in plain)


def test_the_requested_branches_are_the_stores_plus_the_scopes_own(tmp_path, narrow):
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(tmp_path, "env-own"))
    GitPolicyFetcher.set_source_branches(
        {fetcher._source_id: {"env-a", "has space", "bad..name"}}
    )
    assert fetcher._requested_branches() == frozenset({"env-a", "env-own"})
    assert fetcher._scope_branch_refspecs(fetcher._requested_branches()) == [
        "+refs/heads/env-a*:refs/remotes/origin/env-a*",
        "+refs/heads/env-own*:refs/remotes/origin/env-own*",
    ]


def test_too_many_branches_means_the_whole_refspec(tmp_path, narrow, monkeypatch):
    monkeypatch.setattr(git_fetcher, "_MAX_REQUESTED_BRANCHES", 2)
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(tmp_path, "a"))
    GitPolicyFetcher.set_source_branches({fetcher._source_id: {"b", "c"}})
    assert fetcher._requested_branches() is None


def test_no_valid_branch_means_the_whole_refspec(tmp_path, narrow):
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(tmp_path, "bad..name"))
    assert fetcher._requested_branches() is None


@pytest.mark.parametrize(
    "backend, setting", [(FETCH_BACKEND_CLI, False), (FETCH_BACKEND_PYGIT2, True)]
)
def test_narrowing_needs_the_setting_and_the_cli_backend(
    tmp_path, monkeypatch, backend, setting
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_BACKEND", backend)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_SCOPE_BRANCHES", setting)
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(tmp_path, "main"))
    assert fetcher._requested_branches() is None


def test_set_source_branches_replaces_the_whole_map():
    GitPolicyFetcher.set_source_branches({"a": {"x"}, "b": {"y"}})
    GitPolicyFetcher.set_source_branches({"a": {"z"}})
    assert GitPolicyFetcher.source_branches == {"a": frozenset({"z"})}
    assert not GitPolicyFetcher.source_branches_stale(60)


# --- real fetches --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_narrow_fetch_brings_only_the_stores_branches(tmp_path, narrow):
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    # Branches made after the clone: one a scope tracks, one none does, and
    # one whose name starts with the tracked one's (the pattern's known cost).
    _git("-C", str(origin), "branch", "env-a")
    _git("-C", str(origin), "branch", "unused")
    _git("-C", str(origin), "branch", "env-a-other")
    GitPolicyFetcher.set_source_branches({_sid(origin): {"main", "env-a"}})
    fetcher = GitPolicyFetcher(base, "s-main", _source(origin, "main"))

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    refs = _remote_refs(clone)
    assert "refs/remotes/origin/env-a" in refs
    assert "refs/remotes/origin/unused" not in refs
    assert "refs/remotes/origin/env-a-other" in refs  # documented over-match
    assert GitPolicyFetcher.repos_last_fetched_branches[fetcher._source_id] == {
        "main",
        "env-a",
    }


@pytest.mark.asyncio
async def test_a_branch_gone_from_the_remote_does_not_fail_the_fetch(tmp_path, narrow):
    """An exact refspec for a missing branch would fail the whole fetch, and
    with it every scope on the clone; the pattern matches nothing."""
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "c2")
    GitPolicyFetcher.set_source_branches(
        {_sid(origin): {"main", "deleted-env", "also-deleted"}}
    )
    fetcher = GitPolicyFetcher(base, "s-main", _source(origin, "main"))

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetcher._source_id not in GitPolicyFetcher.source_backoff
    assert _head(clone, "refs/remotes/origin/main") == _head(origin, "main")
    assert _head(clone, "refs/remotes/origin/main") == _head(origin, "main")


def test_every_requested_branch_gone_is_no_error(tmp_path):
    origin = _origin(tmp_path)
    clone = tmp_path / "clone"
    _git("clone", "-q", str(origin), str(clone))
    fetched = _cli_fetch(
        clone,
        "origin",
        _source(origin, "x"),
        fetch_timeout=30,
        prune=False,
        refspecs=["+refs/heads/gone-1*:refs/remotes/origin/gone-1*"],
    )
    assert fetched is None


@pytest.mark.asyncio
async def test_prune_leaves_branches_that_were_not_requested(
    tmp_path, narrow, monkeypatch
):
    origin = _origin(tmp_path)
    _git("-C", str(origin), "branch", "other")
    base, clone = await _cloned(tmp_path, origin)  # the clone holds both
    _git("-C", str(origin), "branch", "-D", "other")
    GitPolicyFetcher.set_source_branches({_sid(origin): {"main"}})
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)

    await GitPolicyFetcher(
        base, "s-main", _source(origin, "main")
    ).fetch_and_notify_on_changes(force_fetch=True)

    refs = _remote_refs(clone)
    assert "refs/remotes/origin/main" in refs
    assert "refs/remotes/origin/other" in refs  # not requested: left alone


@pytest.mark.asyncio
async def test_with_the_setting_off_the_cli_fetches_every_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_BACKEND", FETCH_BACKEND_CLI
    )
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    _git("-C", str(origin), "branch", "unused")
    fetcher = GitPolicyFetcher(base, "s-main", _source(origin, "main"))
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert "refs/remotes/origin/unused" in _remote_refs(clone)
    assert GitPolicyFetcher.repos_last_fetched_branches[fetcher._source_id] is None


@pytest.mark.asyncio
async def test_a_narrow_fetch_over_protocol_v2_sends_only_the_requested_prefixes(
    tmp_path, narrow, monkeypatch
):
    """Over v2 the client sends one ref-prefix per requested branch and the
    server advertises only those.

    A local origin speaks v2 through git's file transport;
    GIT_TRACE_PACKET shows the exchange (let through the CLI fetch's env
    allowlist here only).
    """
    origin = _origin(tmp_path)
    for i in range(20):
        _git("-C", str(origin), "branch", f"noise-{i}")
    base, clone = await _cloned(tmp_path, origin)
    _git("-C", str(origin), "branch", "env-a")
    GitPolicyFetcher.set_source_branches({_sid(origin): {"main", "env-a"}})
    trace = tmp_path / "trace"
    monkeypatch.setenv("GIT_TRACE_PACKET", str(trace))
    monkeypatch.setattr(
        git_fetcher,
        "_CLI_FETCH_ENV_ALLOWLIST",
        git_fetcher._CLI_FETCH_ENV_ALLOWLIST + ("GIT_TRACE_PACKET",),
    )

    await GitPolicyFetcher(
        base, "s-main", _source(origin, "main")
    ).fetch_and_notify_on_changes(force_fetch=True)

    text = trace.read_text()
    assert "upload-pack> version 2" in text
    assert "fetch> command=ls-refs" in text
    assert "fetch> ref-prefix refs/heads/env-a" in text
    assert "fetch> ref-prefix refs/heads/main" in text
    assert "ref-prefix refs/tags/" not in text  # --no-tags
    assert "noise-" not in text  # never advertised


# --- a narrow fetch stands in only for the branches it asked for ---------------


@pytest.mark.asyncio
async def test_a_recent_narrow_fetch_does_not_swallow_another_branchs_forced_fetch(
    tmp_path, narrow
):
    """A forced refresh of scope B normally skips its fetch when the source was
    fetched after the request.

    A narrowed fetch that did not ask for B's
    branch must not count: B would otherwise be left without its branch.
    """
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    _git("-C", str(origin), "branch", "env-b")
    shard = GitPolicyFetcher.source_id(_source(origin, "main"))
    if GitPolicyFetcher.source_id(_source(origin, "env-b")) != shard:
        pytest.skip("env-b hashes to another clone shard here")
    req_time = datetime.datetime.now() - datetime.timedelta(seconds=5)
    # A fetch for main only, after B's request.
    GitPolicyFetcher.set_source_branches({shard: {"main"}})
    await GitPolicyFetcher(
        base, "s-main", _source(origin, "main")
    ).fetch_and_notify_on_changes(force_fetch=True)
    assert "refs/remotes/origin/env-b" not in _remote_refs(clone)

    await GitPolicyFetcher(
        base, "s-b", _source(origin, "env-b")
    ).fetch_and_notify_on_changes(force_fetch=True, req_time=req_time)

    assert "refs/remotes/origin/env-b" in _remote_refs(clone)


@pytest.mark.asyncio
async def test_a_recent_narrow_fetch_does_not_swallow_a_forced_fetch_of_a_stale_branch(
    tmp_path, narrow
):
    """The force_fetch case: B's branch is already in the clone, but behind.
    A narrowed fetch after B's request that did not ask for B's branch must
    not stand in for B's forced fetch, or B keeps serving the old head."""
    origin = _origin(tmp_path)
    _git("-C", str(origin), "branch", "env-b")
    shard = GitPolicyFetcher.source_id(_source(origin, "main"))
    if GitPolicyFetcher.source_id(_source(origin, "env-b")) != shard:
        pytest.skip("env-b hashes to another clone shard here")
    base, clone = await _cloned(tmp_path, origin)  # full clone: env-b present
    _git("-C", str(origin), "checkout", "-q", "env-b")
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "b2")
    _git("-C", str(origin), "checkout", "-q", "main")
    req_time = datetime.datetime.now() - datetime.timedelta(seconds=5)
    GitPolicyFetcher.set_source_branches({shard: {"main"}})
    await GitPolicyFetcher(
        base, "s-main", _source(origin, "main")
    ).fetch_and_notify_on_changes(force_fetch=True)
    assert _head(clone, "refs/remotes/origin/env-b") != _head(origin, "env-b")

    await GitPolicyFetcher(
        base, "s-b", _source(origin, "env-b")
    ).fetch_and_notify_on_changes(force_fetch=True, req_time=req_time)

    assert _head(clone, "refs/remotes/origin/env-b") == _head(origin, "env-b")


@pytest.mark.asyncio
async def test_a_missing_branch_is_fetched_unless_a_recent_fetch_asked_for_it(
    tmp_path, narrow
):
    """The unforced case (the sync a bundle request asks for when the scope's
    branch is missing): a fetch after the request stands in for this one only
    if it asked for this branch."""
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    fetcher = GitPolicyFetcher(base, "s-b", _source(origin, "env-b"))
    if fetcher._source_id != _sid(origin):
        pytest.skip("env-b hashes to another clone shard here")
    req_time = datetime.datetime.now() - datetime.timedelta(seconds=5)
    GitPolicyFetcher.repos_last_fetched[fetcher._source_id] = datetime.datetime.now()
    repo = pygit2.Repository(str(clone))

    GitPolicyFetcher.repos_last_fetched_branches[fetcher._source_id] = frozenset(
        {"main"}
    )
    assert await fetcher._should_fetch(repo, req_time=req_time) is True

    GitPolicyFetcher.repos_last_fetched_branches[fetcher._source_id] = frozenset(
        {"main", "env-b"}
    )
    assert await fetcher._should_fetch(repo, req_time=req_time) is False

    GitPolicyFetcher.repos_last_fetched_branches[fetcher._source_id] = None
    assert await fetcher._should_fetch(repo, req_time=req_time) is False


# --- the service keeps the branch sets current --------------------------------


def _scope(origin, scope_id, branch):
    return Scope(scope_id=scope_id, policy=_source(origin, branch))


@pytest.mark.asyncio
async def test_a_sync_pass_fetches_every_scopes_branch(tmp_path, narrow):
    """The pass reads the branch sets from the store before phase 1, so the
    phase-1 fetch of a clone already asks for the phase-2 scopes' branches."""
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    for b in ("env-a", "env-b", "env-c"):
        _git("-C", str(origin), "branch", b)
    shard = GitPolicyFetcher.source_id(_source(origin, "main"))
    scopes = [_scope(origin, "s-main", "main")] + [
        _scope(origin, f"s-{b}", b)
        for b in ("env-a", "env-b", "env-c")
        if GitPolicyFetcher.source_id(_source(origin, b)) == shard
    ]
    service = ScopesService(
        base_dir=base, scopes=FakeScopes(scopes), pubsub_endpoint=NoPubSub()
    )

    await service.sync_scopes(run_due_repacks=False)

    refs = _remote_refs(clone)
    for scope in scopes:
        assert f"refs/remotes/origin/{scope.policy.branch}" in refs


@pytest.mark.asyncio
async def test_a_deleted_scope_drops_out_at_the_next_pass(tmp_path, narrow):
    origin = _origin(tmp_path)
    base, _ = await _cloned(tmp_path, origin)
    store = FakeScopes([_scope(origin, "s-main", "main"), _scope(origin, "s-x", "x")])
    service = ScopesService(base_dir=base, scopes=store, pubsub_endpoint=NoPubSub())
    await service.sync_scopes(run_due_repacks=False)
    sid_x = GitPolicyFetcher.source_id(_source(origin, "x"))
    assert "x" in GitPolicyFetcher.source_branches[sid_x]

    del store.scopes["s-x"]
    await service.sync_scopes(run_due_repacks=False)

    assert "x" not in GitPolicyFetcher.source_branches.get(sid_x, frozenset())


@pytest.mark.asyncio
async def test_a_single_sync_rereads_the_store_only_when_the_sets_are_stale(
    tmp_path, narrow, monkeypatch
):
    origin = _origin(tmp_path)
    base, _ = await _cloned(tmp_path, origin)
    store = FakeScopes([_scope(origin, "s-main", "main")])
    service = ScopesService(base_dir=base, scopes=store, pubsub_endpoint=NoPubSub())

    await service.sync_scope(scope_id="s-main")  # never read: reads
    await service.sync_scope(scope_id="s-main")  # fresh: does not
    assert store.reads == 1

    monkeypatch.setattr(service_module, "_SOURCE_BRANCHES_MAX_AGE", -1.0)
    await service.sync_scope(scope_id="s-main")  # stale: reads again
    assert store.reads == 2


@pytest.mark.asyncio
async def test_with_the_setting_off_a_single_sync_never_reads_the_store(tmp_path):
    origin = _origin(tmp_path)
    base, _ = await _cloned(tmp_path, origin)
    store = FakeScopes([_scope(origin, "s-main", "main")])
    service = ScopesService(base_dir=base, scopes=store, pubsub_endpoint=NoPubSub())
    await service.sync_scope(scope_id="s-main")
    assert store.reads == 0
