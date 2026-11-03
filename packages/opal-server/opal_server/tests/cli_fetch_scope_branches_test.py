"""SCOPES_GIT_FETCH_SCOPE_BRANCHES: with the CLI backend, a fetch asks only
for the branches of the scopes the process tracks on that clone
(PER-17998). Real fetches against local origins with the real git."""

import subprocess
from pathlib import Path

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server import git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    FETCH_BACKEND_CLI,
    FETCH_BACKEND_PYGIT2,
    GitPolicyFetcher,
    _cli_fetch_argv,
)


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


@pytest.fixture(autouse=True)
def clear_fetcher_caches():
    def clear():
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repo_locks.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.source_backoff.clear()
        GitPolicyFetcher.scope_branches.clear()

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


async def _cloned(tmp_path, origin):
    """A clone made by a scope on main; returns (fetcher, clone path)."""
    base = tmp_path / "base"
    fetcher = GitPolicyFetcher(base, "s-main", _source(origin, "main"))
    await fetcher.fetch_and_notify_on_changes()
    return base, Path(GitPolicyFetcher.repo_clone_path(base, _source(origin, "main")))


def test_the_setting_is_off_by_default():
    assert opal_server_config.SCOPES_GIT_FETCH_SCOPE_BRANCHES is False


def test_refspecs_come_on_stdin_with_skipping_negotiation():
    argv = _cli_fetch_argv("/git", "/clone", "origin", False, stdin=True)
    assert argv[-2:] == ["--stdin", "origin"]
    assert argv[argv.index("fetch.negotiationAlgorithm=skipping") - 1] == "-c"
    assert argv.index("fetch.negotiationAlgorithm=skipping") < argv.index("fetch")
    plain = _cli_fetch_argv("/git", "/clone", "origin", False)
    assert "--stdin" not in plain
    assert "fetch.negotiationAlgorithm=skipping" not in plain


def test_each_fetcher_records_its_scope_branch_and_a_delete_forgets_it(tmp_path):
    source = _source(tmp_path, "env-1")
    sid = GitPolicyFetcher.source_id(source)
    GitPolicyFetcher(tmp_path, "s1", source)
    GitPolicyFetcher(tmp_path, "s2", _source(tmp_path, "env-2"))
    assert GitPolicyFetcher.scope_branches[sid] == {"s1": "env-1", "s2": "env-2"}

    GitPolicyFetcher.forget_scope_branch(sid, "s1")
    assert GitPolicyFetcher.scope_branches[sid] == {"s2": "env-2"}
    GitPolicyFetcher.forget_scope_branch(sid, "s2")
    assert sid not in GitPolicyFetcher.scope_branches
    GitPolicyFetcher.forget_scope_branch(sid, "never-there")  # no error


def test_refspecs_are_one_wildcard_patterns_and_skip_invalid_names(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_SCOPE_BRANCHES", True)
    GitPolicyFetcher(tmp_path, "bad", _source(tmp_path, "has space"))
    GitPolicyFetcher(tmp_path, "star", _source(tmp_path, "a*b"))
    fetcher = GitPolicyFetcher(
        tmp_path, "ok", _source(tmp_path, "permit/generated/abc")
    )
    assert fetcher._scope_branch_refspecs() == [
        "+refs/heads/permit/generated/abc*:refs/remotes/origin/permit/generated/abc*"
    ]
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_SCOPE_BRANCHES", False)
    assert fetcher._scope_branch_refspecs() is None


@pytest.mark.asyncio
async def test_a_narrow_fetch_brings_only_the_scopes_branches(tmp_path, narrow):
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    # Branches made after the clone: one a scope tracks, one none does.
    _git("-C", str(origin), "branch", "env-a")
    _git("-C", str(origin), "branch", "unused")
    fetcher = GitPolicyFetcher(base, "s-a", _source(origin, "env-a"))

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    refs = _remote_refs(clone)
    assert "refs/remotes/origin/env-a" in refs
    assert "refs/remotes/origin/unused" not in refs
    # The other scope's branch on the same clone is still updated.
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "c2")
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert _git("-C", str(clone), "rev-parse", "refs/remotes/origin/main") == _git(
        "-C", str(origin), "rev-parse", "main"
    )


@pytest.mark.asyncio
async def test_a_scope_branch_gone_from_the_remote_does_not_fail_the_fetch(
    tmp_path, narrow
):
    """An exact refspec for a missing branch would fail the whole fetch, and
    with it every scope on the clone; the pattern matches nothing."""
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    GitPolicyFetcher(base, "s-gone", _source(origin, "deleted-env"))
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "c2")
    fetcher = GitPolicyFetcher(base, "s-main", _source(origin, "main"))

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetcher._source_id not in GitPolicyFetcher.source_backoff
    assert _git("-C", str(clone), "rev-parse", "refs/remotes/origin/main") == _git(
        "-C", str(origin), "rev-parse", "main"
    )


@pytest.mark.asyncio
async def test_prune_removes_only_a_requested_branch_deleted_on_the_remote(
    tmp_path, narrow, monkeypatch
):
    origin = _origin(tmp_path)
    _git("-C", str(origin), "branch", "env-a")
    _git("-C", str(origin), "branch", "other")
    base, clone = await _cloned(tmp_path, origin)  # the clone holds all three
    fetcher = GitPolicyFetcher(base, "s-a", _source(origin, "env-a"))
    _git("-C", str(origin), "branch", "-D", "env-a")
    _git("-C", str(origin), "branch", "-D", "other")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    refs = _remote_refs(clone)
    assert "refs/remotes/origin/env-a" not in refs  # requested, deleted: pruned
    assert "refs/remotes/origin/other" in refs  # not requested: left alone


@pytest.mark.asyncio
async def test_with_the_setting_off_the_cli_fetches_every_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_BACKEND", FETCH_BACKEND_CLI
    )
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    _git("-C", str(origin), "branch", "unused")
    await GitPolicyFetcher(
        base, "s-main", _source(origin, "main")
    ).fetch_and_notify_on_changes(force_fetch=True)
    assert "refs/remotes/origin/unused" in _remote_refs(clone)


@pytest.mark.asyncio
async def test_the_pygit2_backend_ignores_the_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_BACKEND", FETCH_BACKEND_PYGIT2
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_SCOPE_BRANCHES", True)
    origin = _origin(tmp_path)
    base, clone = await _cloned(tmp_path, origin)
    _git("-C", str(origin), "branch", "unused")
    await GitPolicyFetcher(
        base, "s-main", _source(origin, "main")
    ).fetch_and_notify_on_changes(force_fetch=True)
    assert "refs/remotes/origin/unused" in _remote_refs(clone)


@pytest.mark.asyncio
async def test_a_narrow_fetch_over_protocol_v2_sends_only_the_requested_prefixes(
    tmp_path, narrow, monkeypatch
):
    """The point of the setting: over v2 the client sends one ref-prefix per
    requested branch and the server's advertisement holds only those. A local
    origin speaks v2 through git's file transport, and GIT_TRACE_PACKET shows
    the exchange. GIT_TRACE_PACKET is let through the CLI fetch's env allowlist here only."""
    origin = _origin(tmp_path)
    for i in range(20):
        _git("-C", str(origin), "branch", f"noise-{i}")
    base, clone = await _cloned(tmp_path, origin)
    _git("-C", str(origin), "branch", "env-a")
    fetcher = GitPolicyFetcher(base, "s-a", _source(origin, "env-a"))
    trace = tmp_path / "trace"
    monkeypatch.setenv("GIT_TRACE_PACKET", str(trace))
    monkeypatch.setattr(
        git_fetcher,
        "_CLI_FETCH_ENV_ALLOWLIST",
        git_fetcher._CLI_FETCH_ENV_ALLOWLIST + ("GIT_TRACE_PACKET",),
    )

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    text = trace.read_text()
    assert "upload-pack> version 2" in text
    assert "fetch> command=ls-refs" in text
    assert "fetch> ref-prefix refs/heads/env-a" in text
    assert "fetch> ref-prefix refs/heads/main" in text
    assert "ref-prefix refs/tags/" not in text  # --no-tags
    assert "noise-" not in text  # never advertised
