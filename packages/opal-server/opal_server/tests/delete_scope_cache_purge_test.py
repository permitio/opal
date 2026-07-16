import asyncio

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
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
async def test_delete_unique_scope_purges_caches(tmp_path, monkeypatch):
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    src = scope.policy
    sid = GitPolicyFetcher.source_id(src)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, src))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    GitPolicyFetcher.repo_locks[sid] = asyncio.Lock()

    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree", lambda *a, **k: None
    )

    await svc.delete_scope("only")

    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched
    assert sid not in GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_delete_keeps_caches_when_sibling_shares_source(tmp_path, monkeypatch):
    a = _scope("a", "https://git/shared.git")
    b = _scope("b", "https://git/shared.git")  # same url+branch -> same source_id
    repo = FakeScopeRepository([a, b])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    sid = GitPolicyFetcher.source_id(a.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, a.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    GitPolicyFetcher.repo_locks[sid] = asyncio.Lock()

    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(p),
    )

    await svc.delete_scope("a")

    assert rmtree_calls == []  # sibling shares the source id; clone must survive
    assert clone_path in GitPolicyFetcher.repos
    assert sid in GitPolicyFetcher.repos_last_fetched
    assert sid in GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_concurrent_sibling_deletes_still_purge(tmp_path, monkeypatch):
    """Two concurrent DELETEs of source-sharing scopes must not BOTH skip the
    purge (TOCTOU on the sibling check) — whichever finishes last must
    purge."""
    a = _scope("a", "https://git/shared.git")
    b = _scope("b", "https://git/shared.git")
    repo = FakeScopeRepository([a, b])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    sid = GitPolicyFetcher.source_id(a.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, a.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(str(p)),
    )

    await asyncio.gather(svc.delete_scope("a"), svc.delete_scope("b"))

    assert rmtree_calls == [
        clone_path
    ], "concurrent sibling deletes both skipped the purge (TOCTOU)"
    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched


class _AllRaisesAfterDeleteRepository(FakeScopeRepository):
    """All() blows up only on the post-delete sibling re-check (e.g. a
    transient store error or one malformed record failing parse_raw)."""

    def __init__(self, scopes):
        super().__init__(scopes)
        self.deleted_once = False

    async def delete(self, scope_id):
        await super().delete(scope_id)
        self.deleted_once = True

    async def all(self):
        if self.deleted_once:
            raise RuntimeError("store scan failed (malformed record)")
        return await super().all()


@pytest.mark.asyncio
async def test_sibling_check_failure_still_purges(tmp_path, monkeypatch):
    """If the post-delete sibling re-check raises, the purge must still run:

    the record is already deleted, so the client's retry is a 204 no-op
    (ScopeNotFoundError) and a skipped purge is a permanent leak. Over-
    purging is safe — a surviving sibling re-clones on its next sync.
    """
    scope = _scope("only", "https://git/repo-a.git")
    repo = _AllRaisesAfterDeleteRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(str(p)),
    )

    from opal_common.logger import logger as opal_logger

    records = []
    sink_id = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        # Must not raise: the re-check failure is downgraded to a warning.
        await svc.delete_scope("only")
    finally:
        opal_logger.remove(sink_id)

    assert rmtree_calls == [clone_path], (
        "sibling re-check failure skipped the purge — permanent leak "
        "(retry is a 204 no-op, the purge is unreachable)"
    )
    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched
    assert any(
        "sibling check failed" in r and "purging defensively" in r for r in records
    ), f"defensive purge not logged: {records}"


@pytest.mark.asyncio
async def test_delete_purges_when_sibling_shares_url_but_not_source(
    tmp_path, monkeypatch
):
    """Same url, different branch, sharded clones (SCOPES_REPO_CLONES_SHARDS>1)
    resolve to different source_ids -> different clone dirs.

    Deleting one must still purge its own clone + caches; the url-
    sharing sibling lives elsewhere.
    """
    # shards=4: branch "main" -> index 1, "dev" -> index 3 (distinct source_ids).
    monkeypatch.setattr(
        "opal_server.git_fetcher.opal_server_config.SCOPES_REPO_CLONES_SHARDS", 4
    )
    a = _scope("a", "https://git/shared.git", branch="main")
    b = _scope("b", "https://git/shared.git", branch="dev")  # same url, diff source_id
    assert GitPolicyFetcher.source_id(a.policy) != GitPolicyFetcher.source_id(b.policy)

    repo = FakeScopeRepository([a, b])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    sid_a = GitPolicyFetcher.source_id(a.policy)
    clone_path_a = str(GitPolicyFetcher.repo_clone_path(tmp_path, a.policy))
    GitPolicyFetcher.repos[clone_path_a] = object()
    GitPolicyFetcher.repos_last_fetched[sid_a] = "ts"

    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(str(p)),
    )

    await svc.delete_scope("a")

    assert rmtree_calls == [clone_path_a]  # its own clone dir removed
    assert clone_path_a not in GitPolicyFetcher.repos
    assert sid_a not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_delete_serializes_against_inflight_repo_lock(tmp_path, monkeypatch):
    """The purge must wait for the repo lock held by an in-flight fetch —
    otherwise it rmtree's the clone and free()s the pygit2 handle out from
    under the fetch thread."""
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()

    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(str(p)),
    )

    # Simulate an in-flight fetch holding the repo lock.
    lock = GitPolicyFetcher.repo_locks.setdefault(sid, asyncio.Lock())
    await lock.acquire()
    try:
        delete_task = asyncio.create_task(svc.delete_scope("only"))
        for _ in range(10):  # give the delete every chance to (wrongly) proceed
            await asyncio.sleep(0)
        assert not delete_task.done(), "delete_scope did not wait for the repo lock"
        assert rmtree_calls == [], "purge ran while the fetch held the repo lock"
    finally:
        lock.release()

    await asyncio.wait_for(delete_task, timeout=5)
    assert rmtree_calls == [clone_path]
    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_lock_source_waiter_retries_after_delete_pops_entry():
    """A waiter queued on the old lock must not proceed under it once a delete
    popped the entry — it retries and serializes on the freshly-minted lock."""
    sid = "some-source-id"
    events = []

    async def deleter():
        async with GitPolicyFetcher.lock_source(sid):
            events.append("deleter-in")
            await asyncio.sleep(0.01)  # let the waiter queue on this lock
            GitPolicyFetcher.repo_locks.pop(sid, None)
        events.append("deleter-out")

    async def waiter():
        async with GitPolicyFetcher.lock_source(sid):
            events.append("waiter-in")
            # We must hold the *current* dict entry, not the popped one.
            assert GitPolicyFetcher.repo_locks.get(sid) is not None

    await asyncio.gather(deleter(), waiter())
    assert events == ["deleter-in", "deleter-out", "waiter-in"]


class _AmbiguousDeleteRepository(FakeScopeRepository):
    """Delete commits server-side but the client sees an error (classic
    dropped-connection/timeout ambiguous store outcome)."""

    async def delete(self, scope_id):
        await super().delete(scope_id)
        raise ConnectionError("connection dropped after the delete committed")


@pytest.mark.asyncio
async def test_purge_still_runs_when_record_delete_raises_ambiguously(
    tmp_path, monkeypatch
):
    """If the record delete commits but raises to the caller, the purge must
    still run: the record is gone, so a client retry is a 204 no-op
    (ScopeNotFoundError) and a purge gated on a clean delete is permanently
    orphaned. The error must still propagate (the client sees a 500 and can
    retry)."""
    scope = _scope("only", "https://git/repo-a.git")
    repo = _AmbiguousDeleteRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(str(p)),
    )

    with pytest.raises(ConnectionError):
        await svc.delete_scope("only")

    assert rmtree_calls == [clone_path], (
        "record-delete failure skipped the purge — the retry is a 204 no-op, "
        "so the clone and cache entries leak permanently"
    )
    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched
    assert sid not in GitPolicyFetcher.repo_locks


class _DeletedAfterSnapshotRepository(FakeScopeRepository):
    """All() still returns the scope (a stale sync_scopes snapshot); get()
    reports it deleted — models a DELETE landing between the two."""

    async def get(self, scope_id):
        await asyncio.sleep(0)
        raise ScopeNotFoundError(scope_id)


@pytest.mark.asyncio
async def test_sync_scopes_skips_scope_deleted_after_snapshot(tmp_path, monkeypatch):
    """A scope deleted between sync_scopes' all() snapshot and its queued
    sync_scope call must not be fetched — re-cloning it would re-populate
    repos/repos_last_fetched/repo_locks for a dead scope (leaked until
    restart)."""
    scope = _scope("dead", "https://git/repo-a.git")
    repo = _DeletedAfterSnapshotRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    fetch_calls = []

    async def fake_fetch(self, *args, **kwargs):
        fetch_calls.append(self._scope_id)

    monkeypatch.setattr(GitPolicyFetcher, "fetch_and_notify_on_changes", fake_fetch)

    await svc.sync_scopes()  # must not raise: the delete race is expected

    assert fetch_calls == [], "sync fetched a scope whose delete already landed"
    assert not GitPolicyFetcher.repos
    assert not GitPolicyFetcher.repos_last_fetched
    assert not GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_recreate_after_delete_serializes_and_sees_clean_caches(
    tmp_path, monkeypatch
):
    """A re-create's first sync queued during a delete must run only after the
    purge completed, on the freshly-minted lock, and see empty caches."""
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree", lambda *a, **k: None
    )

    order = []
    gate = GitPolicyFetcher.repo_locks.setdefault(sid, asyncio.Lock())
    await gate.acquire()  # simulate the in-flight fetch the delete must wait on
    try:

        async def deleter():
            await svc.delete_scope("only")
            order.append("delete-done")

        async def recreator():  # stands in for the re-created scope's first sync
            async with GitPolicyFetcher.lock_source(sid):
                order.append(("recreate-in", clone_path in GitPolicyFetcher.repos))

        d = asyncio.create_task(deleter())
        for _ in range(5):
            await asyncio.sleep(0)  # deleter queues on the held lock first
        r = asyncio.create_task(recreator())
        for _ in range(5):
            await asyncio.sleep(0)  # recreator queues behind it
    finally:
        gate.release()

    await asyncio.wait_for(asyncio.gather(d, r), timeout=5)
    assert order == ["delete-done", ("recreate-in", False)]
