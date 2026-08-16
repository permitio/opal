"""DELETE /scopes/{id}: record delete + local memory purge + purge broadcast.

Disk mutation moved to the leader's purge handler (purge_channel_test.py);
these tests pin the route-side contract. Two PR2-era tests are kept verbatim
at the bottom: the lock_source waiter-retry invariant and the stale-snapshot
sync skip — both still hold unchanged.
"""
import asyncio
import pathlib

import pytest
from fastapi import FastAPI
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    _mark_git_op_done,
    _mark_git_op_started,
)
from opal_server.scopes import api as opal_server_api
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
    await svc.delete_scope("only")

    # Only the publish contract is asserted here. The cache state at this
    # instant depends on whether the backgrounded floor has been scheduled yet —
    # asserting either way would be a coin flip on the fake's timing, and
    # "local memory is untouched" stopped being the contract when the floor
    # landed. The floor's effect is pinned deterministically by the tests below,
    # which drain it.
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
    purge owned that case; since the disk-reclaim cut, nothing does —
    the dir stays until PER-15612.
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


@pytest.mark.asyncio
async def test_local_floor_keeps_the_clone_of_a_re_created_scope(tmp_path):
    """DELETE + re-create of the SAME scope id on the SAME source, before the
    backgrounded floor runs.

    The floor's sibling check must not exclude the deleted scope_id: excluding
    it blinds the check to the re-created record and the rmtree then takes a
    live scope's clone. Delete-then-re-create is a normal workflow — the bed has
    test_delete_recreate_storm.

    Mutation: passing scope_id as excluded_scope_id to find_scope_sharing_source
    (what master did, and what this shipped as) fails here.
    """
    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    repo = FakeScopeRepository([scope])
    svc = ScopesService(
        base_dir=tmp_path, scopes=repo, pubsub_endpoint=FakePubSubEndpoint()
    )

    await svc.delete_scope("only")
    # the operator re-creates it on the same source before the floor runs
    repo._scopes["only"] = _scope("only", "https://git/repo-a.git")
    await _drain_floor(svc)

    assert clone.exists(), "the floor deleted a live re-created scope's clone"


@pytest.mark.asyncio
async def test_local_floor_keeps_the_clone_when_the_sibling_check_raises(tmp_path):
    """A store blip must not take a live tenant's policy offline.

    Master purged defensively on any scan failure. Here that would rmtree a
    clone a sibling scope may still share, 503ing that tenant until the
    re-clone finishes — triggered by a transient Redis error, which is far more
    common than the ambiguous-delete case master was protecting against. The
    cost of keeping is an orphan dir (PER-15612).

    Mutation: restoring `sharer = None` on the exception fails here.
    """

    class _RaisingStore(FakeScopeRepository):
        async def all(self):
            raise RuntimeError("store scan failed")

    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=_RaisingStore([scope]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    await svc.delete_scope("only")
    await _drain_floor(svc)

    assert clone.exists(), "a store fault deleted a clone a sibling may still share"


@pytest.mark.asyncio
async def test_service_stop_drains_the_floor(tmp_path):
    """A DELETE returns 204, then SIGTERM arrives. Without a drain the floor is
    a detached task nobody references and the dir survives with nothing left to
    reclaim it.

    Mutation: making ScopesService.stop() a no-op fails here.
    """
    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    await svc.delete_scope("only")
    assert svc._local_purges, "nothing was spawned to drain"
    await svc.stop()

    assert not svc._local_purges, "stop() returned with the floor still in flight"
    assert not clone.exists(), "the drained floor never completed"


@pytest.mark.asyncio
async def test_floor_early_returns_drain_the_repo_lock(tmp_path):
    """lock_source MINTS an entry on the way in, so an early return leaks one
    for a source nothing holds — invariant I4, which the leader path enforces
    with a finally and this one did not.

    Uses the in-flight branch (the source really is dead, so draining is
    correct); the live-sibling branch is deliberately excluded and is covered by
    test_local_floor_keeps_the_clone_when_a_sibling_shares_the_source.

    Mutation: dropping the `finally` fails here.
    """
    scope = _scope("only", "https://git/repo-a.git")
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    sid = GitPolicyFetcher.source_id(scope.policy)
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
    assert sid not in GitPolicyFetcher.repo_locks, "early return leaked a lock (I4)"


@pytest.mark.asyncio
async def test_floor_refuses_a_path_that_is_not_the_derived_one(tmp_path, monkeypatch):
    """Every other destructive path derives its target from source_id and
    refuses a mismatch. This one took the caller's Path — not wire-controlled,
    but it was the one rmtree in the series skipping the check.

    Mutation: the guard is DISJUNCTIVE — the comparison short-circuits before
    the rmtree, and the body separately operates on the derived path. Removing
    EITHER alone leaves this green; only removing BOTH deletes the decoy. An
    earlier version of this docstring claimed the revert alone killed it, which
    is false, and invited a reader to drop the comparison as "only an
    assertion". Belt and braces, deliberately, and stated as such.
    """
    scope = _scope("only", "https://git/repo-a.git")
    decoy = tmp_path / "not-a-clone-dir"
    decoy.mkdir()
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )
    monkeypatch.setattr(
        GitPolicyFetcher, "repo_clone_path", staticmethod(lambda *a, **k: decoy)
    )

    await svc.delete_scope("only")
    await _drain_floor(svc)

    assert decoy.exists(), "rmtree'd a path that is not the derived clone dir"


@pytest.mark.asyncio
async def test_shutdown_drains_the_routers_scopes_service(tmp_path, monkeypatch):
    """The drain must target the instance init_scope_router received.

    There are TWO ScopesService objects per process: the one server.py builds
    for the router (which delete_scope runs on, so its _local_purges holds the
    floor tasks) and a second one ScopesPolicyWatcherTask builds for itself. An
    earlier version drained the watcher's — always an empty set — so a DELETE
    followed by SIGTERM stranded the clone dir, which is a regression against
    the merge base, where the rmtree completed before the 204.

    This asserts on the object the router was handed, because that is the only
    thing the bug could distinguish. Both prior tests used a locally built or
    hand-injected service and passed throughout.

    Mutation: pointing OpalServer._drain_scopes_service at any other instance,
    or dropping it from stop_server_background_tasks, fails here.
    """
    from opal_server.server import OpalServer

    captured = {}
    real_init = opal_server_api.init_scope_router

    def _capture(scopes, authenticator, pubsub_endpoint, scopes_service):
        captured["service"] = scopes_service
        return real_init(scopes, authenticator, pubsub_endpoint, scopes_service)

    monkeypatch.setattr("opal_server.server.init_scope_router", _capture)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))

    from opal_common.authentication.signer import JWTSigner
    from opal_common.authentication.types import JWTAlgorithm

    server = OpalServer.__new__(OpalServer)
    server._scopes_service = None
    server._scopes = FakeScopeRepository([_scope("only", "https://git/repo-a.git")])
    server.watcher = None
    server.publisher = None
    server.broadcast_keepalive = None
    server.opal_statistics = None
    server.jwks_endpoint = None
    server.master_token = None
    server.loadlimit_notation = None
    server.data_sources_config = None
    # keys=None -> verifier disabled, which is all the router needs here
    server.signer = JWTSigner(
        private_key=None,
        public_key=None,
        algorithm=getattr(JWTAlgorithm, "RS256"),
        audience="test",
        issuer="test",
    )

    from fastapi import APIRouter

    class _FakePubSub:
        endpoint = FakePubSubEndpoint()
        pubsub_router = APIRouter()
        api_router = APIRouter()

    server.pubsub = _FakePubSub()
    app = FastAPI()
    server._configure_api_routes(app)

    assert (
        captured["service"] is server._scopes_service
    ), "the drained instance is not the one the router serves DELETE on"

    # a real pending floor task on that instance must be awaited by shutdown
    drained = []

    async def _slow_floor():
        await asyncio.sleep(0.05)
        drained.append(True)

    task = asyncio.create_task(_slow_floor())
    server._scopes_service._local_purges.add(task)
    task.add_done_callback(server._scopes_service._local_purges.discard)

    await server.stop_server_background_tasks()

    assert drained == [True], "shutdown returned without awaiting the floor"


@pytest.mark.asyncio
async def test_floor_keeps_a_live_siblings_repo_lock_entry(tmp_path):
    """The floor's copy of d359ffb2's I4 fix had no test.

    The leader's identical guard is pinned by two tests; this one — the copy
    that runs on whichever worker served the DELETE — reddened nothing. The
    bed's test_shared_repo_survives_sibling_scope_delete does not cover it
    either: single-worker against a healthy backbone, so the LEADER's
    confirmation drives the drain and the floor's branch is never isolated.

    Mutation: removing `minted = None` on the floor's live-sibling path fails
    here.
    """
    doomed = _scope("doomed", "https://git/shared.git")
    sibling = _scope("sibling", "https://git/shared.git")
    sid = GitPolicyFetcher.source_id(doomed.policy)
    assert sid == GitPolicyFetcher.source_id(sibling.policy)
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, doomed.policy)
    clone.mkdir(parents=True)
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([doomed, sibling]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    await svc.delete_scope("doomed")
    await _drain_floor(svc)

    assert clone.exists(), "purged a clone a live sibling still shares"
    assert (
        sid in GitPolicyFetcher.repo_locks
    ), "drained the lock entry of a source a live sibling is actively using"


@pytest.mark.asyncio
async def test_floor_aborts_when_the_derived_path_disagrees(tmp_path, monkeypatch):
    """The confinement COMPARISON must abort the floor, not merely assert.

    An earlier version of this pin only died when the derived-path usage was
    ALSO reverted, so the comparison itself was unpinned and its docstring said
    so — which invites deleting it. Here the DERIVED path is real and populated
    while the caller's scope_dir points elsewhere: with the comparison removed
    the floor proceeds and rmtree's the derived path, which is exactly the
    mismatch the check exists to refuse.

    Mutation: removing `if safe_path is None or safe_path != str(scope_dir)`
    fails here.
    """
    from opal_server.scopes.purge import confined_clone_path

    scope = _scope("only", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(scope.policy)
    derived = pathlib.Path(confined_clone_path(tmp_path, sid))
    derived.mkdir(parents=True)
    (derived / "marker").write_text("x")

    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    monkeypatch.setattr(
        GitPolicyFetcher, "repo_clone_path", staticmethod(lambda *a, **k: elsewhere)
    )

    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=FakePubSubEndpoint(),
    )
    await svc.delete_scope("only")
    await _drain_floor(svc)

    assert derived.exists(), (
        "the floor acted on the derived path even though the caller's path "
        "disagreed — the mismatch must abort, not be silently reconciled"
    )
    assert elsewhere.exists(), "rmtree'd the caller-supplied path"
