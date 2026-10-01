"""Scope-liveness check before clone (resurrection class).

A delete landing DURING a sync must not let the sync re-clone the dead
scope's repo (bed gate: the delete-vs-sync exclusion in
test_randomized_churn_holds_invariants is lifted once this holds).
"""
import asyncio

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService


def _source(url="https://git/repo-a.git"):
    return GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="main",
        auth=NoAuthData(auth_type="none"),
    )


@pytest.fixture(autouse=True)
def clear_caches():
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    yield
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()


def _fetcher(tmp_path, probe):
    return GitPolicyFetcher(tmp_path, "scope-1", _source(), liveness_probe=probe)


async def _run_with_clone_recorder(fetcher, monkeypatch):
    clones = []

    async def fake_clone(self):
        clones.append(True)

    monkeypatch.setattr(GitPolicyFetcher, "_clone", fake_clone)
    await fetcher.fetch_and_notify_on_changes()
    return clones


@pytest.mark.asyncio
async def test_dead_scope_is_not_cloned(tmp_path, monkeypatch):
    async def probe():
        return False  # scope was deleted mid-sync

    clones = await _run_with_clone_recorder(_fetcher(tmp_path, probe), monkeypatch)
    assert clones == [], "sync resurrected a deleted scope's clone"


@pytest.mark.asyncio
async def test_live_scope_is_cloned(tmp_path, monkeypatch):
    async def probe():
        return True

    clones = await _run_with_clone_recorder(_fetcher(tmp_path, probe), monkeypatch)
    assert clones == [True]


@pytest.mark.asyncio
async def test_no_probe_clones(tmp_path, monkeypatch):
    clones = await _run_with_clone_recorder(_fetcher(tmp_path, None), monkeypatch)
    assert clones == [True]


@pytest.mark.asyncio
async def test_raising_probe_fails_open(tmp_path, monkeypatch):
    """A store hiccup must not block the sync — proceed with the clone."""

    async def probe():
        raise RuntimeError("redis flaked")

    clones = await _run_with_clone_recorder(_fetcher(tmp_path, probe), monkeypatch)
    assert clones == [True]


class FakeScopeRepository:
    """Minimal ScopeRepository stand-in: ``get`` always returns whatever
    scope was configured, regardless of the id passed in — enough to
    simulate a repoint (the stored record now differs from the one the
    caller started syncing)."""

    def __init__(self, scope):
        self._scope = scope

    async def get(self, scope_id):
        await asyncio.sleep(0)
        if self._scope is None:
            raise ScopeNotFoundError(scope_id)
        return self._scope


def _git_scope(scope_id, url, branch="main"):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=url,
            branch=branch,
            auth=NoAuthData(auth_type="none"),
        ),
        data={"entries": []},
    )


async def _sync_with_clone_recorder(svc, scope, monkeypatch):
    clones = []

    async def fake_clone(self):
        clones.append(True)

    monkeypatch.setattr(GitPolicyFetcher, "_clone", fake_clone)
    await svc.sync_scope(scope=scope, notify_on_changes=False)
    return clones


@pytest.mark.asyncio
async def test_repointed_scope_is_not_cloned_against_stale_source(
    tmp_path, monkeypatch
):
    """PER-15157 J2: a sync that captured source A before a PUT repoints the
    scope to source B must not re-clone A — the repoint already purged A's
    cache entries, so cloning it again would strand a dir that
    nothing reclaims (no later purge names that source; PER-15612's sweep is
    what would eventually catch it)."""
    stale = _git_scope("scope-1", "https://git/repo-a.git")
    repointed = _git_scope("scope-1", "https://git/repo-b.git")
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository(repointed),
        pubsub_endpoint=None,
    )

    clones = await _sync_with_clone_recorder(svc, stale, monkeypatch)
    assert clones == [], "sync re-cloned a source the scope no longer points at"


@pytest.mark.asyncio
async def test_unrepointed_scope_still_clones(tmp_path, monkeypatch):
    """Control: an unchanged source must still clone — the probe must not
    over-reject."""
    scope = _git_scope("scope-1", "https://git/repo-a.git")
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository(scope),
        pubsub_endpoint=None,
    )

    clones = await _sync_with_clone_recorder(svc, scope, monkeypatch)
    assert clones == [True]


@pytest.mark.asyncio
async def test_deleted_scope_is_not_cloned_through_real_closure(tmp_path, monkeypatch):
    """Delete-resurrection counterpart to
    test_repointed_scope_is_not_cloned_against_stale_source: a delete landing
    mid-sync must not let the REAL ScopesService closure (not the hand-rolled
    probe above) clone a deleted scope's repo — ``_scope_still_exists``'s
    ``except ScopeNotFoundError: return False`` branch must actually fire."""
    stale = _git_scope("scope-1", "https://git/repo-a.git")
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository(None),  # get() raises ScopeNotFoundError
        pubsub_endpoint=None,
    )

    clones = await _sync_with_clone_recorder(svc, stale, monkeypatch)
    assert clones == [], "sync resurrected a deleted scope's clone"
