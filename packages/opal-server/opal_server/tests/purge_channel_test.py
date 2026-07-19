import asyncio

import pytest
from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    _mark_git_op_done,
    _mark_git_op_started,
)
from opal_server.scopes.purge import (
    ScopePurgeCommand,
    handle_purge_message,
    purge_local_memory,
    subscribe_worker_purge_handler,
)


def test_purge_channel_config_default():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_PURGE_CHANNEL == "__opal_scope_purge__"


@pytest.fixture(autouse=True)
def clear_caches():
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    yield
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()


def _cmd(sid="sid-1", path="/clones/sid-1", confirmed=False):
    return ScopePurgeCommand(
        source_id=sid, clone_path=path, scope_id="s1", reason="delete",
        confirmed=confirmed,
    )


def test_purge_local_memory_pops_repo_and_timestamp_but_never_locks():
    GitPolicyFetcher.repos["/clones/sid-1"] = object()
    GitPolicyFetcher.repos_last_fetched["sid-1"] = "ts"
    lock = asyncio.Lock()
    GitPolicyFetcher.repo_locks["sid-1"] = lock

    purge_local_memory("sid-1", "/clones/sid-1")

    assert "/clones/sid-1" not in GitPolicyFetcher.repos
    assert "sid-1" not in GitPolicyFetcher.repos_last_fetched
    # Lock-identity invariant: only lock holders may pop repo_locks.
    assert GitPolicyFetcher.repo_locks["sid-1"] is lock


def test_purge_local_memory_skips_forget_repo_while_git_op_in_flight():
    """Freeing a pygit2 handle while a pool thread still uses it is a crash
    risk — the handle must survive; the timestamp pop is still safe."""
    GitPolicyFetcher.repos["/clones/sid-1"] = object()
    GitPolicyFetcher.repos_last_fetched["sid-1"] = "ts"
    _mark_git_op_started("sid-1")
    try:
        purge_local_memory("sid-1", "/clones/sid-1")
    finally:
        _mark_git_op_done("sid-1")

    assert "/clones/sid-1" in GitPolicyFetcher.repos  # handle survived
    assert "sid-1" not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_handle_purge_message_parses_and_purges():
    GitPolicyFetcher.repos["/clones/sid-1"] = object()
    GitPolicyFetcher.repos_last_fetched["sid-1"] = "ts"

    await handle_purge_message(None, _cmd(confirmed=True).dict())

    assert "/clones/sid-1" not in GitPolicyFetcher.repos
    assert "sid-1" not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_handle_purge_message_ignores_unconfirmed_requests():
    """Workers must not purge on a raw request — only the leader's
    sibling-checked confirmation may drop cache entries (over-purge of a
    shared source was a bed regression)."""
    GitPolicyFetcher.repos["/clones/sid-1"] = object()
    GitPolicyFetcher.repos_last_fetched["sid-1"] = "ts"

    await handle_purge_message(None, _cmd().dict())  # confirmed defaults False

    assert "/clones/sid-1" in GitPolicyFetcher.repos
    assert "sid-1" in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_handle_purge_message_tolerates_garbage_payload():
    # Must not raise — a bad message must never kill the subscription.
    await handle_purge_message(None, {"nonsense": True})
    await handle_purge_message(None, None)
    await handle_purge_message(None, "not-a-dict")


@pytest.mark.asyncio
async def test_subscribe_worker_purge_handler_wires_channel():
    class FakeEndpoint:
        def __init__(self):
            self.subs = []

        async def subscribe(self, topics, callback):
            self.subs.append((list(topics), callback))

    ep = FakeEndpoint()
    await subscribe_worker_purge_handler(ep)
    assert ep.subs == [(["__opal_scope_purge__"], handle_purge_message)]


import shutil

from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.scopes.purge import LeaderScopePurger
from opal_server.scopes.scope_repository import ScopeNotFoundError


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


def _make_clone(tmp_path, source):
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, source)
    clone.mkdir(parents=True)
    (clone / "marker").write_text("x")
    return clone


@pytest.mark.asyncio
async def test_leader_purges_unshared_source_from_disk(tmp_path):
    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)
    GitPolicyFetcher.repos[str(clone)] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    GitPolicyFetcher.repo_locks[sid] = asyncio.Lock()

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id=sid, clone_path=str(clone), scope_id="dead", reason="delete"
        ).dict(),
    )
    await task

    assert not clone.exists()
    assert str(clone) not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched
    assert sid not in GitPolicyFetcher.repo_locks  # popped under the held lock


@pytest.mark.asyncio
async def test_leader_keeps_disk_when_live_sibling_shares_source(tmp_path):
    survivor = _scope("survivor", "https://git/shared.git")
    sid = GitPolicyFetcher.source_id(survivor.policy)
    clone = _make_clone(tmp_path, survivor.policy)

    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([survivor]),
        pubsub_endpoint=None,
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id=sid,
            clone_path=str(clone),
            scope_id="deleted-sibling",
            reason="delete",
        ).dict(),
    )
    await task

    assert clone.exists(), "shared clone must survive a sibling's delete"


@pytest.mark.asyncio
async def test_leader_skips_disk_while_git_op_in_flight(tmp_path):
    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    _mark_git_op_started(sid)
    try:
        task = await purger.handle(
            None,
            ScopePurgeCommand(
                source_id=sid,
                clone_path=str(clone),
                scope_id="dead",
                reason="delete",
            ).dict(),
        )
        await task
    finally:
        _mark_git_op_done(sid)

    assert clone.exists(), "rmtree while a git thread touches the repo is unsafe"
    # The orphan sweep is the backstop that reclaims it later (Task 8).


@pytest.mark.asyncio
async def test_leader_purges_defensively_when_sibling_check_raises(tmp_path):
    """PR2 semantics transfer: if the store scan raises, purge anyway —
    under-purging is a permanent leak, over-purging self-heals via re-clone."""

    class BrokenRepo(FakeScopeRepository):
        async def all(self):
            raise RuntimeError("store scan failed")

    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=BrokenRepo([]), pubsub_endpoint=None
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id=sid, clone_path=str(clone), scope_id="dead", reason="delete"
        ).dict(),
    )
    await task

    assert not clone.exists()


@pytest.mark.asyncio
async def test_leader_handle_returns_fast_and_purge_waits_for_lock(tmp_path):
    """Handle() must return promptly even while the source lock is held (the
    publish path awaits it inline — DELETE/PUT latency contract), while the
    background purge still serializes on the lock."""
    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    lock = GitPolicyFetcher.repo_locks.setdefault(sid, asyncio.Lock())
    await lock.acquire()
    try:
        task = await asyncio.wait_for(
            purger.handle(
                None,
                ScopePurgeCommand(
                    source_id=sid,
                    clone_path=str(clone),
                    scope_id="dead",
                    reason="delete",
                ).dict(),
            ),
            timeout=1,
        )
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done(), "purge ran while the fetch held the source lock"
        assert clone.exists()
    finally:
        lock.release()

    await asyncio.wait_for(task, timeout=5)
    assert not clone.exists()


@pytest.mark.asyncio
async def test_leader_handle_tolerates_garbage_payload(tmp_path):
    """A malformed purge message must never raise out of the leader handler — a
    raised exception could kill the pub/sub subscription."""
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    assert await purger.handle(None, {"nonsense": True}) is None
    assert await purger.handle(None, None) is None
    assert await purger.handle(None, "not-a-dict") is None


@pytest.mark.asyncio
async def test_leader_ignores_confirmation_broadcasts(tmp_path):
    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id=sid, clone_path=str(clone), scope_id="dead",
            reason="delete", confirmed=True,
        ).dict(),
    )
    assert task is None
    assert clone.exists(), "leader acted on its own confirmation broadcast"


@pytest.mark.asyncio
async def test_leader_publishes_confirmation_after_purge(tmp_path):
    class FakePubSubEndpoint:
        def __init__(self):
            self.published = []

        async def publish(self, topics, data=None):
            self.published.append((list(topics), data))

    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)
    pubsub = FakePubSubEndpoint()
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=pubsub
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id=sid, clone_path=str(clone), scope_id="dead",
            reason="delete",
        ).dict(),
    )
    await task
    assert not clone.exists()
    assert len(pubsub.published) == 1
    _, payload = pubsub.published[0]
    assert payload["confirmed"] is True
    assert payload["source_id"] == sid


@pytest.mark.asyncio
async def test_leader_does_not_confirm_when_shared_or_inflight(tmp_path):
    survivor = _scope("survivor", "https://git/shared.git")
    sid = GitPolicyFetcher.source_id(survivor.policy)
    clone = _make_clone(tmp_path, survivor.policy)

    class FakePubSubEndpoint:
        def __init__(self):
            self.published = []

        async def publish(self, topics, data=None):
            self.published.append((list(topics), data))

    pubsub = FakePubSubEndpoint()
    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([survivor]),
        pubsub_endpoint=pubsub,
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id=sid, clone_path=str(clone), scope_id="deleted-sibling",
            reason="delete",
        ).dict(),
    )
    await task
    assert pubsub.published == []  # shared → no confirmation

    inflight_purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([]),
        pubsub_endpoint=pubsub,
    )
    _mark_git_op_started(sid)
    try:
        task = await inflight_purger.handle(
            None,
            ScopePurgeCommand(
                source_id=sid, clone_path=str(clone), scope_id="x",
                reason="delete",
            ).dict(),
        )
        await task
    finally:
        _mark_git_op_done(sid)
    assert pubsub.published == []  # deferred → no confirmation
