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
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    _mark_git_op_done,
    _mark_git_op_started,
)
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


async def _drain_floor(svc):
    """Await the best-effort local clone purge delete_scope spawns.

    It is deliberately backgrounded (DELETE's latency is bounded by
    contract), so a test that asserts on its effect without draining is
    a coin flip.
    """
    while svc._local_purges:
        await asyncio.gather(*list(svc._local_purges), return_exceptions=True)


@pytest.mark.asyncio
async def test_delete_publishes_request_without_touching_local_memory(tmp_path):
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

    # Fleet-wide, caches drop on the leader's confirmation broadcast. On THIS
    # worker they also drop from the local floor — but only once it has run,
    # which is why the request-side assertions come first.
    assert clone_path in GitPolicyFetcher.repos
    assert sid in GitPolicyFetcher.repos_last_fetched
    assert GitPolicyFetcher.repo_locks[sid] is lock
    assert len(pubsub.published) == 1
    topics, payload = pubsub.published[0]
    assert topics == [opal_server_config.SCOPES_PURGE_CHANNEL]
    assert payload == {
        "source_id": sid,
        "clone_path": clone_path,
        "scope_id": "only",
        "reason": "delete",
        "confirmed": False,
    }


@pytest.mark.asyncio
async def test_delete_reclaims_this_workers_clone_as_a_floor(tmp_path):
    """Master removed the clone dir INLINE in the DELETE-serving process, with
    no broadcast involved. The fleet purge that replaced it is droppable at
    shipped defaults, so without a local floor the lost-broadcast case is a
    regression against the merge base rather than parity with it.

    Mutation: dropping the _purge_local_clone_best_effort task leaves the dir
    and the cache entries and fails here.
    """
    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    sid = GitPolicyFetcher.source_id(scope.policy)
    GitPolicyFetcher.repos[str(clone)] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    GitPolicyFetcher.repo_locks[sid] = asyncio.Lock()
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    await svc.delete_scope("only")
    await _drain_floor(svc)

    assert not clone.exists(), "the serving worker's own copy was never reclaimed"
    assert str(clone) not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched
    assert sid not in GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_local_floor_keeps_the_clone_when_a_sibling_shares_the_source(tmp_path):
    """The floor is master's sibling-checked purge, not an unconditional
    rmtree: a surviving scope on the same source_id still needs the clone."""
    doomed = _scope("doomed", "https://git/shared.git")
    sibling = _scope("sibling", "https://git/shared.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, doomed.policy)
    clone.mkdir(parents=True)
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([doomed, sibling]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    await svc.delete_scope("doomed")
    await _drain_floor(svc)

    assert clone.exists(), "purged a clone a live sibling scope still shares"


@pytest.mark.asyncio
async def test_local_floor_skips_while_a_git_op_is_in_flight(tmp_path):
    """Master freed the handle unconditionally here.

    Freeing one a lingering timed-out pygit2 call still holds on a pool
    thread is the use-after-free class 89e090be fixed — the leader's
    purge (and its deferred retry) owns that case instead.
    """
    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    sid = GitPolicyFetcher.source_id(scope.policy)
    GitPolicyFetcher.repos[str(clone)] = object()
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    _mark_git_op_started(sid)
    try:
        await svc.delete_scope("only")
        await _drain_floor(svc)
    finally:
        _mark_git_op_done(sid)

    assert clone.exists(), "rmtree while a git thread touches the repo is unsafe"
    assert str(clone) in GitPolicyFetcher.repos, "handle freed under a live thread"


@pytest.mark.asyncio
async def test_delete_without_pubsub_endpoint_still_reclaims_locally(tmp_path):
    """pubsub_endpoint=None (preload path / degraded mode) must not crash.

    With no broadcast there is no leader-side purge at all, so the local
    floor is the ONLY thing that reclaims — which is the case master
    covered and the publish-only version did not.
    """
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    await svc.delete_scope("only")
    await _drain_floor(svc)

    with pytest.raises(ScopeNotFoundError):
        await repo.get("only")
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
    clean delete would orphan the leader-side purge permanently.

    The error still propagates.
    """
    scope = _scope("only", "https://git/repo-a.git")
    repo = _AmbiguousDeleteRepository([scope])
    pubsub = FakePubSubEndpoint()
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub)
    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()

    with pytest.raises(ConnectionError):
        await svc.delete_scope("only")

    assert len(pubsub.published) == 1


# ---- PR2-era invariants that transfer unchanged ---------------------------


@pytest.mark.asyncio
async def test_lock_source_waiter_retries_after_delete_pops_entry():
    """A waiter queued on the old lock must not proceed under it once a holder
    popped the entry — it retries on the freshly-minted lock."""
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


class _RaisingPubSubEndpoint:
    """A broadcaster that is down.

    SCOPES_PURGE_CHANNEL is freeze-exempt, so a publish during a
    backbone gap is attempted and fails rather than deferred.
    """

    async def publish(self, topics, data=None):
        raise ConnectionError("broadcaster is down")


@pytest.mark.asyncio
async def test_floor_runs_even_when_the_purge_publish_raises(tmp_path):
    """The degraded case is the whole reason the floor exists, so the floor
    must not be downstream of the thing that is degraded.

    publish() can raise a broadcaster error (LeaderScopePurger._purge_and_log
    documents exactly that), and it runs in delete_scope's `finally`, so
    scheduling the floor after it skips the floor precisely when the broadcast
    is lost — the dir then leaks with nothing to reclaim it.

    Mutation: moving the create_task below the publish must fail here.
    """
    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    sid = GitPolicyFetcher.source_id(scope.policy)
    GitPolicyFetcher.repos[str(clone)] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=_RaisingPubSubEndpoint(),
    )

    # The broadcaster error still propagates — the caller must not be told the
    # fleet purge succeeded.
    with pytest.raises(ConnectionError):
        await svc.delete_scope("only")
    await _drain_floor(svc)

    assert not clone.exists(), "floor skipped when the purge broadcast failed"
    assert str(clone) not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched
