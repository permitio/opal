"""Scope-liveness check before clone (resurrection class).

A delete landing DURING a sync must not let the sync re-clone the dead
scope's repo (bed gate: the delete-vs-sync exclusion in
test_randomized_churn_holds_invariants is lifted once this holds)."""
import asyncio

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server.git_fetcher import GitPolicyFetcher


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
    return GitPolicyFetcher(
        tmp_path, "scope-1", _source(), liveness_probe=probe
    )


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
