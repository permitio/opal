"""Leader-only reconciliation sweep: clone dirs referencing no live scope are
reclaimed (bed gates: test_orphan_clone_dir_is_reclaimed,
test_redis_wiped_boot_reclaims_clones, red half of
test_shard_reconfig_still_serves_but_orphans_old_clones)."""
import asyncio

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    _mark_git_op_done,
    _mark_git_op_started,
)
from opal_server.scopes.purge import LeaderScopePurger
from opal_server.scopes.scope_repository import ScopeNotFoundError


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())


class FakePubSubEndpoint:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((list(topics), data))


def _scope(scope_id, url, branch="main"):
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


@pytest.fixture(autouse=True)
def clear_caches():
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    yield
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()


def _git_sources(tmp_path):
    d = GitPolicyFetcher.base_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clone_dir_for(tmp_path, scope):
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    (clone / "marker").write_text("x")
    return clone


@pytest.mark.asyncio
async def test_orphan_dir_reclaimed_live_dir_kept(tmp_path):
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / "deadbeef-0"
    orphan.mkdir()
    pubsub = FakePubSubEndpoint()

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=pubsub
    )
    await purger.sweep_orphans()

    assert not orphan.exists()
    assert live_clone.exists()
    assert len(pubsub.published) == 1
    topics, payload = pubsub.published[0]
    assert topics == [opal_server_config.SCOPES_PURGE_CHANNEL]
    assert payload["source_id"] == "deadbeef-0"
    assert payload["reason"] == "orphan"
    assert payload["confirmed"] is True


@pytest.mark.asyncio
async def test_redis_wiped_boot_reclaims_everything(tmp_path):
    a = _clone_dir_for(tmp_path, _scope("a", "https://git/a.git"))
    b = _clone_dir_for(tmp_path, _scope("b", "https://git/b.git"))

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    await purger.sweep_orphans()

    assert not a.exists() and not b.exists()


@pytest.mark.asyncio
async def test_store_error_aborts_sweep_without_deleting(tmp_path):
    """A transient store error must abort the ENTIRE sweep before the per-entry
    loop — not be read as 'no scopes exist' (which would rmtree every live
    clone).

    The call-count assertion proves the abort happened at the initial
    scan, independent of the per-entry recheck's own guard.
    """

    class BrokenOnceRepo(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.all_calls = 0

        async def all(self):
            self.all_calls += 1
            if self.all_calls == 1:
                raise RuntimeError("redis down")
            return await super().all()

    live_clone = _clone_dir_for(tmp_path, _scope("live", "https://git/live.git"))
    orphan = _git_sources(tmp_path) / "deadbeef-0"
    orphan.mkdir()
    pubsub = FakePubSubEndpoint()
    repo = BrokenOnceRepo([])  # empty: if the sweep wrongly continued with
    # live=set(), the recheck (a second .all() call) would succeed and
    # delete BOTH dirs — every assertion below discriminates.

    purger = LeaderScopePurger(base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub)
    await purger.sweep_orphans()  # must not raise

    assert repo.all_calls == 1, "sweep continued past the failed initial scan"
    assert live_clone.exists() and orphan.exists()
    assert pubsub.published == []


@pytest.mark.asyncio
async def test_inflight_orphan_is_skipped(tmp_path):
    orphan = _git_sources(tmp_path) / "busy-source-0"
    orphan.mkdir()

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    _mark_git_op_started("busy-source-0")
    try:
        await purger.sweep_orphans()
    finally:
        _mark_git_op_done("busy-source-0")

    assert orphan.exists(), "swept a dir a lingering git op still touches"


@pytest.mark.asyncio
async def test_non_directory_junk_is_ignored(tmp_path):
    junk = _git_sources(tmp_path) / "stray-file"
    junk.write_text("not a clone")

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    await purger.sweep_orphans()

    assert junk.exists()


@pytest.mark.asyncio
async def test_missing_base_dir_is_a_noop(tmp_path):
    purger = LeaderScopePurger(
        base_dir=tmp_path / "never-created",
        scopes=FakeScopeRepository([]),
        pubsub_endpoint=None,
    )
    await purger.sweep_orphans()  # must not raise
