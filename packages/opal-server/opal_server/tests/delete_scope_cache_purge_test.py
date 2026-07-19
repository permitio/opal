"""DELETE /scopes/{id}: record delete + local memory purge + purge broadcast.

Disk mutation moved to the leader's purge handler (purge_channel_test.py);
these tests pin the route-side contract. Two PR2-era tests are kept verbatim
at the bottom: the lock_source waiter-retry invariant and the stale-snapshot
sync skip — both still hold unchanged.
"""
import asyncio

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        await asyncio.sleep(0)
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        await asyncio.sleep(0)
        return list(self._scopes.values())

    async def delete(self, scope_id):
        await asyncio.sleep(0)
        self._scopes.pop(scope_id, None)


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


@pytest.mark.asyncio
async def test_delete_purges_local_memory_and_publishes(tmp_path):
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    pubsub = FakePubSubEndpoint()
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub)

    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    lock = asyncio.Lock()
    GitPolicyFetcher.repo_locks[sid] = lock

    await svc.delete_scope("only")

    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched
    # Route-side purge never pops locks (only the lock holder may).
    assert GitPolicyFetcher.repo_locks[sid] is lock
    assert len(pubsub.published) == 1
    topics, payload = pubsub.published[0]
    assert topics == [opal_server_config.SCOPES_PURGE_CHANNEL]
    assert payload == {
        "source_id": sid,
        "clone_path": clone_path,
        "scope_id": "only",
        "reason": "delete",
    }


@pytest.mark.asyncio
async def test_delete_does_not_touch_disk(tmp_path):
    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    await svc.delete_scope("only")

    assert clone.exists(), "disk mutation belongs to the leader's handler"


@pytest.mark.asyncio
async def test_delete_without_pubsub_endpoint_still_purges_local(tmp_path):
    """pubsub_endpoint=None (preload path / degraded mode) must not crash and
    must still drop local memory."""
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    await svc.delete_scope("only")

    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_delete_non_git_scope_deletes_record_only(tmp_path):
    # Scope.policy is a required field typed Union[GitPolicyScopeSource] (the
    # only concrete policy-source type today), so a non-git policy can't be
    # constructed through normal validation; .construct() bypasses it to
    # exercise the isinstance() early-return branch directly.
    scope = Scope.construct(scope_id="plain", policy=None, data={"entries": []})
    repo = FakeScopeRepository([scope])
    pubsub = FakePubSubEndpoint()
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub)

    await svc.delete_scope("plain")

    with pytest.raises(ScopeNotFoundError):
        await repo.get("plain")
    assert pubsub.published == []


class _AmbiguousDeleteRepository(FakeScopeRepository):
    """Delete commits server-side but the client sees an error."""

    async def delete(self, scope_id):
        await super().delete(scope_id)
        raise ConnectionError("connection dropped after the delete committed")


@pytest.mark.asyncio
async def test_publish_still_runs_when_record_delete_raises_ambiguously(tmp_path):
    """The retry is a 204 no-op (ScopeNotFoundError), so a publish gated on a
    clean delete would orphan the leader-side purge permanently. The error
    still propagates."""
    scope = _scope("only", "https://git/repo-a.git")
    repo = _AmbiguousDeleteRepository([scope])
    pubsub = FakePubSubEndpoint()
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub)
    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()

    with pytest.raises(ConnectionError):
        await svc.delete_scope("only")

    assert clone_path not in GitPolicyFetcher.repos
    assert len(pubsub.published) == 1


# ---- PR2-era invariants that transfer unchanged ---------------------------


@pytest.mark.asyncio
async def test_lock_source_waiter_retries_after_delete_pops_entry():
    """A waiter queued on the old lock must not proceed under it once a
    holder popped the entry — it retries on the freshly-minted lock."""
    sid = "some-source-id"
    events = []

    async def deleter():
        async with GitPolicyFetcher.lock_source(sid):
            events.append("deleter-in")
            await asyncio.sleep(0.01)
            GitPolicyFetcher.repo_locks.pop(sid, None)
        events.append("deleter-out")

    async def waiter():
        async with GitPolicyFetcher.lock_source(sid):
            events.append("waiter-in")
            assert GitPolicyFetcher.repo_locks.get(sid) is not None

    await asyncio.gather(deleter(), waiter())
    assert events == ["deleter-in", "deleter-out", "waiter-in"]


class _DeletedAfterSnapshotRepository(FakeScopeRepository):
    async def get(self, scope_id):
        await asyncio.sleep(0)
        raise ScopeNotFoundError(scope_id)


@pytest.mark.asyncio
async def test_sync_scopes_skips_scope_deleted_after_snapshot(tmp_path, monkeypatch):
    scope = _scope("dead", "https://git/repo-a.git")
    repo = _DeletedAfterSnapshotRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    fetch_calls = []

    async def fake_fetch(self, *args, **kwargs):
        fetch_calls.append(self._scope_id)

    monkeypatch.setattr(GitPolicyFetcher, "fetch_and_notify_on_changes", fake_fetch)

    await svc.sync_scopes()

    assert fetch_calls == []
    assert not GitPolicyFetcher.repos
    assert not GitPolicyFetcher.repos_last_fetched
    assert not GitPolicyFetcher.repo_locks
