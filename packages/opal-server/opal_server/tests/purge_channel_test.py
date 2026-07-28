import asyncio
from pathlib import Path

import pytest
from opal_server.config import OpalServerConfig, opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    _mark_git_op_done,
    _mark_git_op_started,
)
from opal_server.pubsub import PubSub
from opal_server.scopes.purge import (
    ScopePurgeCommand,
    handle_purge_message,
    purge_local_memory,
    subscribe_worker_purge_handler,
)


def test_purge_channel_config_default():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_PURGE_CHANNEL == "__opal_scope_purge__"


def test_orphan_sweep_interval_config_default():
    assert OpalServerConfig(prefix="OPAL_").SCOPES_ORPHAN_SWEEP_INTERVAL == 300


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
        source_id=sid,
        clone_path=path,
        scope_id="s1",
        reason="delete",
        confirmed=confirmed,
    )


def _real_sid():
    # 64 hex + shard index, matching GitPolicyFetcher.source_id's shape
    return "a" * 64 + "-0"


def _derived_path(base_dir, sid):
    return str(GitPolicyFetcher.base_dir(Path(base_dir)) / sid)


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
async def test_handle_purge_message_parses_and_purges(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "opal_server.scopes.purge.opal_server_config.BASE_DIR", str(tmp_path)
    )
    sid = _real_sid()
    path = _derived_path(tmp_path, sid)
    GitPolicyFetcher.repos[path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    await handle_purge_message(None, _cmd(sid=sid, path=path, confirmed=True).dict())

    assert path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_handle_purge_message_leaves_no_stray_repo_lock(tmp_path, monkeypatch):
    """The worker handler takes lock_source (minting a repo_locks entry via
    setdefault), so it must pop it under the lock — otherwise every purged
    source leaks a lock (invariant I4; the git-leak bed's churn tests catch it
    the hard way)."""
    monkeypatch.setattr(
        "opal_server.scopes.purge.opal_server_config.BASE_DIR", str(tmp_path)
    )
    sid = _real_sid()
    path = _derived_path(tmp_path, sid)
    GitPolicyFetcher.repos[path] = object()

    await handle_purge_message(None, _cmd(sid=sid, path=path, confirmed=True).dict())

    assert sid not in GitPolicyFetcher.repo_locks, "worker purge left a stray lock"


@pytest.mark.asyncio
async def test_handle_purge_message_ignores_unconfirmed_requests(tmp_path, monkeypatch):
    """Workers must not purge on a raw request — only the leader's sibling-
    checked confirmation may drop cache entries (over-purge of a shared source
    was a bed regression).

    Uses a VALID source_id and seeds the cache at its DERIVED path, so the ONLY
    thing that can stop the purge is the `confirmed` gate. With the old
    `sid="sid-1"` the handler returned at the malformed-source_id branch instead
    (after the gate), so the test passed even with the gate deleted and never
    actually observed it.
    """
    monkeypatch.setattr(
        "opal_server.scopes.purge.opal_server_config.BASE_DIR", str(tmp_path)
    )
    sid = _real_sid()
    path = _derived_path(tmp_path, sid)
    GitPolicyFetcher.repos[path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    # confirmed defaults False -> a raw request; the gate must stop it.
    await handle_purge_message(None, _cmd(sid=sid, path=path).dict())

    assert path in GitPolicyFetcher.repos
    assert sid in GitPolicyFetcher.repos_last_fetched


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


def test_purge_channel_is_freeze_exempt_under_custom_name(monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_PURGE_CHANNEL", "scope_purge_custom"
    )
    ps = PubSub(signer=object(), broadcaster_uri=None)  # signer only stored, not called
    assert "scope_purge_custom" in ps.endpoint._freeze_exempt_topics
    assert ps.endpoint._is_exempt(["scope_purge_custom"]) is True


# --- F1: SCOPES_PURGE_CHANNEL is server-internal; external RPC peers (clients/
# PDPs) must not be able to publish or subscribe to it (a forged purge would
# churn the whole fleet's caches). The restriction runs only when a channel is
# present (external peer); legitimate server/broadcaster traffic is channel=None
# and never reaches it. See PubSub._reject_external_purge_channel. ---
from fastapi_websocket_pubsub import ALL_TOPICS  # noqa: E402
from opal_common.authentication.verifier import Unauthorized  # noqa: E402
from opal_common.config import opal_common_config  # noqa: E402


def test_purge_restriction_is_registered_on_the_notifier():
    ps = PubSub(signer=object(), broadcaster_uri=None)
    assert PubSub._reject_external_purge_channel in ps.notifier._channel_restrictions


# NOTE: these await the restriction directly under @pytest.mark.asyncio rather
# than asyncio.run(...). asyncio.run() closes its loop and leaves the current
# loop set to None, which on Python 3.9 breaks later SYNC tests that call
# asyncio.get_event_loop() (e.g. reconnecting_broadcaster_test) — the same
# py3.9 event-loop-isolation trap as commit 8400a75e.
@pytest.mark.asyncio
async def test_external_peer_publish_to_purge_channel_is_rejected():
    with pytest.raises(Unauthorized):
        await PubSub._reject_external_purge_channel(
            [opal_server_config.SCOPES_PURGE_CHANNEL], object()
        )


@pytest.mark.asyncio
async def test_external_peer_rejected_even_when_purge_channel_mixed_with_others():
    with pytest.raises(Unauthorized):
        await PubSub._reject_external_purge_channel(
            ["policy:some_dir", opal_server_config.SCOPES_PURGE_CHANNEL], object()
        )


@pytest.mark.asyncio
async def test_client_stats_channel_publish_is_not_affected():
    # The ONLY channel a real opal-client publishes to (STATISTICS enabled).
    # Must still pass — proves the fix does not touch legitimate client traffic
    # and needs no client change/redeploy.
    await PubSub._reject_external_purge_channel(
        [opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL], object()
    )


@pytest.mark.asyncio
async def test_ordinary_client_topics_are_not_affected():
    await PubSub._reject_external_purge_channel(
        ["policy:dir_a", "data:tenant/x"], object()
    )


@pytest.mark.asyncio
async def test_external_peer_cannot_subscribe_all_topics():
    # ALL_TOPICS must be rejected too: the same callback guards subscribe, and
    # notify() fans every published topic (purge included) to the ALL_TOPICS
    # subscriber bucket, so an ALL_TOPICS subscriber would receive purge
    # traffic. No opal-client subscribes to ALL_TOPICS (only the broadcaster,
    # which is channel=None and never reaches this callback).
    with pytest.raises(Unauthorized):
        await PubSub._reject_external_purge_channel(ALL_TOPICS, object())


import shutil

from opal_common.logger import logger
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.scopes.purge import LeaderScopePurger, find_scope_sharing_source
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
async def test_leader_inflight_defers_disk_but_drains_lock_and_timestamp(tmp_path):
    """With a lingering git op: the clone dir and the (thread-visible) repo
    handle must survive, but the lock/timestamp entries drain and the purge
    is confirmed — the repoint-during-hung-fetch gate measures exactly the
    lock/timestamp drain."""

    class FakePubSubEndpoint:
        def __init__(self):
            self.published = []

        async def publish(self, topics, data=None):
            self.published.append((list(topics), data))

    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)
    GitPolicyFetcher.repos[str(clone)] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"
    GitPolicyFetcher.repo_locks[sid] = asyncio.Lock()
    pubsub = FakePubSubEndpoint()

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=pubsub
    )
    _mark_git_op_started(sid)
    try:
        task = await purger.handle(
            None,
            ScopePurgeCommand(
                source_id=sid,
                clone_path=str(clone),
                scope_id="dead",
                reason="repoint",
            ).dict(),
        )
        await task
    finally:
        _mark_git_op_done(sid)

    assert clone.exists(), "rmtree while a git thread touches the repo is unsafe"
    assert str(clone) in GitPolicyFetcher.repos, "handle freed under a live thread"
    assert sid not in GitPolicyFetcher.repos_last_fetched
    assert sid not in GitPolicyFetcher.repo_locks
    assert len(pubsub.published) == 1
    _, payload = pubsub.published[0]
    assert payload["confirmed"] is True


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
    warnings = []
    sink_id = logger.add(lambda m: warnings.append(str(m)), level="WARNING")
    try:
        task = await purger.handle(
            None,
            ScopePurgeCommand(
                source_id=sid, clone_path=str(clone), scope_id="dead", reason="delete"
            ).dict(),
        )
        await task
    finally:
        logger.remove(sink_id)

    assert not clone.exists()
    assert any("purging defensively" in w for w in warnings), f"not emitted: {warnings}"


@pytest.mark.asyncio
async def test_leader_keeps_clone_on_repoint_when_sibling_check_raises(
    tmp_path, monkeypatch
):
    """Repoint's old-source purge must NOT fail open when the sibling check
    raises: the record for the reused source_id still exists (it was just
    repointed elsewhere), so a defensive purge would delete a clone a live
    scope may still reference. Delete keeps its fail-open (the tested
    behavior above): its record is already gone, so under-purging leaks
    forever while over-purging self-heals via re-clone."""
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))

    class RaisingRepo:
        async def all(self):
            raise RuntimeError("store scan failed")

    sid = _real_sid()
    clone = Path(_derived_path(tmp_path, sid))
    clone.mkdir(parents=True)
    purger = LeaderScopePurger(
        base_dir=Path(tmp_path), scopes=RaisingRepo(), pubsub_endpoint=None
    )
    await purger.purge_source_if_unshared(
        ScopePurgeCommand(
            source_id=sid, clone_path=str(clone), scope_id="s1", reason="repoint"
        )
    )
    assert clone.exists(), "repoint must not purge defensively on a raising scan"


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
            source_id=sid,
            clone_path=str(clone),
            scope_id="dead",
            reason="delete",
            confirmed=True,
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
            source_id=sid,
            clone_path=str(clone),
            scope_id="dead",
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
async def test_leader_does_not_confirm_when_shared(tmp_path):
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
            source_id=sid,
            clone_path=str(clone),
            scope_id="deleted-sibling",
            reason="delete",
        ).dict(),
    )
    await task
    assert pubsub.published == []  # shared → no confirmation


@pytest.mark.asyncio
async def test_confirmation_is_published_while_holding_the_source_lock(tmp_path):
    """The confirmation frees this process's pygit2 handle via the inline local
    subscriber. It MUST be published under lock_source, or a re-created scope's
    sync can cache a fresh handle in the gap and have it freed mid-
    _notify_on_changes (use-after-free).

    Discriminates by capturing the lock object BEFORE the purge runs, then
    checking ``.locked()`` from inside the fake endpoint's ``publish()``.
    ``publish()`` runs on the purge's own task, so this is a same-task state
    check, not a cross-task race: if the publish call happens before the
    ``async with`` block has exited, the lock is still held and ``.locked()``
    is True; if it happens after, the lock was already released and
    ``.locked()`` is False. The lock is popped from ``repo_locks`` under the
    lock before the confirm, so this check must use the captured reference,
    not a fresh dict lookup.
    """
    dead = _scope("dead", "https://git/repo-a.git")
    sid = GitPolicyFetcher.source_id(dead.policy)
    clone = _make_clone(tmp_path, dead.policy)
    # Capture the lock object the purge will acquire, before it runs.
    source_lock = GitPolicyFetcher.repo_locks.setdefault(sid, asyncio.Lock())
    lock_state_at_publish = []

    class LockProbingEndpoint:
        async def publish(self, topics, data=None):
            lock_state_at_publish.append(source_lock.locked())

    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([]),
        pubsub_endpoint=LockProbingEndpoint(),
    )
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
    assert lock_state_at_publish == [
        True
    ], f"confirmation published outside lock_source: {lock_state_at_publish}"


@pytest.mark.asyncio
async def test_leader_ignores_forged_clone_path(tmp_path):
    """A forged clone_path must never be deleted — only the path DERIVED from
    source_id is touched."""
    import os

    forged = tmp_path / "victim"
    forged.mkdir()
    (forged / "keep").write_text("x")
    # a real clone that SHOULD be purged, under the derived location
    sid = GitPolicyFetcher.source_id(_scope("d", "https://git/repo-a.git").policy)
    derived = GitPolicyFetcher.base_dir(tmp_path) / sid
    derived.mkdir(parents=True)
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id=sid,
            clone_path=str(forged),  # <-- forged path
            scope_id="d",
            reason="delete",
        ).dict(),
    )
    await task
    assert forged.exists(), "forged clone_path was deleted — path came off the wire"
    assert not derived.exists(), "the real (derived) clone dir should be purged"


@pytest.mark.asyncio
async def test_leader_rejects_malformed_source_id(tmp_path):
    evil = tmp_path / "evil"
    evil.mkdir()
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    task = await purger.handle(
        None,
        ScopePurgeCommand(
            source_id="../../etc",
            clone_path=str(evil),
            scope_id="d",
            reason="delete",
        ).dict(),
    )
    if task is not None:
        await task
    assert evil.exists()


@pytest.mark.asyncio
async def test_concurrent_purges_for_shared_source_do_not_both_skip(tmp_path):
    a = _scope("a", "https://git/shared.git")
    b = _scope("b", "https://git/shared.git")
    sid = GitPolicyFetcher.source_id(a.policy)
    assert sid == GitPolicyFetcher.source_id(b.policy)
    clone = _make_clone(tmp_path, a.policy)
    repo = FakeScopeRepository([a, b])
    purger = LeaderScopePurger(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    async def delete_then_purge(scope_id):
        await repo.delete(scope_id)
        task = await purger.handle(
            None,
            ScopePurgeCommand(
                source_id=sid, clone_path=str(clone), scope_id=scope_id, reason="delete"
            ).dict(),
        )
        await task

    await asyncio.gather(delete_then_purge("a"), delete_then_purge("b"))
    assert not clone.exists(), "both purges skipped — shared source leaked"


@pytest.mark.asyncio
async def test_find_scope_sharing_source_distinguishes_shards(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 4)
    a = _scope("a", "https://git/shared.git", branch="main")
    b = _scope("b", "https://git/shared.git", branch="prod")
    sid_a, sid_b = GitPolicyFetcher.source_id(a.policy), GitPolicyFetcher.source_id(
        b.policy
    )
    assert sid_a != sid_b
    repo = FakeScopeRepository([b])
    assert await find_scope_sharing_source(repo, sid_a) is None
    assert await find_scope_sharing_source(repo, sid_b) == "b"


@pytest.mark.asyncio
async def test_recreate_after_delete_serializes_and_sees_clean_caches(
    tmp_path, monkeypatch
):
    """The third dropped PR2 regression, ported to the fleet-purge design.

    A re-created scope's first sync queued while the leader is purging
    the old source must run only AFTER the purge completes, on the
    freshly-minted lock, and see clean caches — never the stale pygit2
    handle the purge is about to free. Delete and purge are no longer
    synchronous, so lock_source is the only thing serializing them; this
    is the use-after-free the confirmation-under- lock discipline exists
    to prevent.
    """
    monkeypatch.setattr(
        "opal_server.scopes.purge.opal_server_config.BASE_DIR", str(tmp_path)
    )
    monkeypatch.setattr("opal_server.scopes.purge.shutil.rmtree", lambda *a, **k: None)
    sid = _real_sid()
    clone_path = _derived_path(tmp_path, sid)
    GitPolicyFetcher.repos[clone_path] = object()  # stale handle from before the delete

    # Leader purge for a source no live scope maps to (it was deleted): purges
    # under lock_source, dropping the cached handle.
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    cmd = _cmd(sid=sid, path=clone_path, confirmed=False)

    order = []
    gate = GitPolicyFetcher.repo_locks.setdefault(sid, asyncio.Lock())
    await gate.acquire()  # stands in for the in-flight op the purge queues behind
    try:

        async def deleter():
            await purger.purge_source_if_unshared(cmd)
            order.append("purge-done")

        async def recreator():  # the re-created scope's first sync
            async with GitPolicyFetcher.lock_source(sid):
                order.append(("recreate-in", clone_path in GitPolicyFetcher.repos))

        d = asyncio.create_task(deleter())
        for _ in range(5):
            await asyncio.sleep(0)  # purge queues on the held lock first
        r = asyncio.create_task(recreator())
        for _ in range(5):
            await asyncio.sleep(0)  # recreate queues behind it
    finally:
        gate.release()

    await asyncio.wait_for(asyncio.gather(d, r), timeout=5)
    # Recreate ran AFTER the purge, and saw the handle already gone (clean caches).
    assert order == ["purge-done", ("recreate-in", False)]
