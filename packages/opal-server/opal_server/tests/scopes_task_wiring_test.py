"""ScopesPolicyWatcherTask wiring: what start(), stop() and trigger() must
actually do — the periodic-polling timer, the fire-and-forget sync wrapper, the
boot and refresh-all sync paths, and the leader purge subscription's separate
subscriber id. Unit-pins them so a refactor can't silently drop one."""
import asyncio

import pytest
from opal_server.scopes.task import ScopesPolicyWatcherTask


class _Recorder:
    def __init__(self, events, fail_sync=False):
        self._events = events
        self._fail_sync = fail_sync

    async def sync_scopes(self, *args, **kwargs):
        self._events.append("sync")
        if self._fail_sync:
            raise RuntimeError("store scan failed")

    async def sync_scope(self, *args, **kwargs):
        self._events.append("sync_one")

    async def handle(self, *args, **kwargs):  # the purge-channel subscriber
        return None


class FakeNotifier:
    """Minimal stand-in for EventNotifier's subscriber-id API."""

    def __init__(self):
        self.subs = []
        self.unsubs = []
        self._minted = 0

    def gen_subscriber_id(self):
        self._minted += 1
        return f"fake-sub-{self._minted}"

    async def subscribe(self, subscriber_id, topics, callback):
        self.subs.append((subscriber_id, list(topics), callback))

    async def unsubscribe(self, subscriber_id, topics=None):
        self.unsubs.append((subscriber_id, list(topics) if topics else None))


def _bare_task(events, fail_sync=False):
    """Construct without __init__ (it needs Redis); wire only what the methods
    under test use."""
    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    rec = _Recorder(events, fail_sync=fail_sync)
    t._service = rec
    t._purger = rec
    return t


@pytest.mark.asyncio
async def test_single_scope_trigger_does_not_sync_all():
    """A single-scope refresh must dispatch to sync_scope, never fall through
    to the refresh-all branch (which would re-sync every scope on every
    webhook)."""
    events = []
    await _bare_task(events).trigger(topic=None, data={"scope_id": "s1"})
    assert events == ["sync_one"]


@pytest.mark.asyncio
async def test_periodic_polling_survives_a_raising_sync(monkeypatch):
    # A raising sync_scopes in a poll pass must be caught (logged) and the loop
    # kept alive — one store hiccup must not kill periodic sync.
    from opal_server.config import opal_server_config

    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0.001)
    events = []
    task = asyncio.create_task(_bare_task(events, fail_sync=True)._periodic_polling())
    try:
        # Bounded, and it asserts the task is ALIVE each turn. Spinning on
        # `while events.count("sync") < 2` alone wedges forever the moment the
        # loop dies — so stripping the try/except under test hung the run
        # instead of reddening it, and there is no pytest-timeout in the unit
        # suite's dependencies to catch that.
        for _ in range(10_000):
            if events.count("sync") >= 2:
                break
            assert not task.done(), (
                "the polling loop died on a raising sync instead of surviving "
                f"it: {task.exception() if task.done() else None!r}"
            )
            await asyncio.sleep(0)
        assert events.count("sync") >= 2, "the polling loop never ran twice"
        assert not task.done()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_start_subscribes_leader_purge_handler(monkeypatch):
    from opal_server.config import opal_server_config
    from opal_server.policy.watcher.task import BasePolicyWatcherTask

    async def _noop_start(self):
        return None

    monkeypatch.setattr(BasePolicyWatcherTask, "start", _noop_start)
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)

    class FakeEndpoint:
        def __init__(self):
            self.notifier = FakeNotifier()

    class FakePurger:
        async def handle(self, *a, **k):
            return None

    class FakeService:
        async def sync_scopes(self, *a, **k):
            return None

    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    t._pubsub_endpoint = FakeEndpoint()
    t._purger = FakePurger()
    t._service = FakeService()
    t._tasks = []
    t._purger_sub_id = None
    await t.start()
    try:
        # Registered under its OWN subscriber id (not the endpoint's shared one),
        # so stop() can remove it without dropping the every-worker handler.
        assert t._pubsub_endpoint.notifier.subs == [
            (
                t._purger_sub_id,
                [opal_server_config.SCOPES_PURGE_CHANNEL],
                t._purger.handle,
            )
        ]
        assert t._purger_sub_id is not None
    finally:
        for task in t._tasks:
            task.cancel()
        await asyncio.gather(*t._tasks, return_exceptions=True)


# --- Round-3 review: ~35 lines of new lifecycle code had zero coverage, and
# both fixes in this file shipped green when reverted. One test per mutation. ---


class _FakeEndpoint:
    def __init__(self):
        self.notifier = FakeNotifier()


def _purge_cmd(sid, confirmed):
    return {
        "source_id": sid,
        "clone_path": f"/clones/{sid}",
        "scope_id": "s1",
        "reason": "delete",
        "confirmed": confirmed,
    }


@pytest.fixture
def _clean_fetcher_caches():
    from opal_server.git_fetcher import GitPolicyFetcher

    caches = (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
    )
    for d in caches:
        d.clear()
    yield
    for d in caches:
        d.clear()


@pytest.mark.asyncio
async def test_stop_does_not_unsubscribe_the_every_worker_purge_handler(
    tmp_path, monkeypatch, _clean_fetcher_caches
):
    """Stop() must remove ONLY the leader's subscription.

    PubSubEndpoint files every server-side subscription under one shared
    subscriber id, and EventNotifier.unsubscribe deletes that id's whole
    callback list for the topic — so unsubscribing by topic here would also drop
    handle_purge_message, which server.py registers once at boot for every
    worker and nothing ever re-adds. The process stays up (uvicorn drains
    in-flight requests) while silently ignoring every fleet purge.

    Mutation: `await self._pubsub_endpoint.unsubscribe([CHANNEL])` must fail.
    """
    from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
    from opal_server.config import opal_server_config
    from opal_server.git_fetcher import GitPolicyFetcher
    from opal_server.policy.watcher.task import BasePolicyWatcherTask
    from opal_server.scopes.purge import subscribe_worker_purge_handler

    async def _noop_start(self):
        return None

    monkeypatch.setattr(BasePolicyWatcherTask, "start", _noop_start)
    monkeypatch.setattr(
        "opal_server.scopes.purge.opal_server_config.BASE_DIR", str(tmp_path)
    )
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)

    endpoint = PubSubEndpoint()  # real EventNotifier
    await subscribe_worker_purge_handler(endpoint)  # boot-time, every worker

    sid = "a" * 64 + "-0"
    cached_path = str(GitPolicyFetcher.base_dir(tmp_path) / sid)
    GitPolicyFetcher.repos[cached_path] = object()

    leader_calls = []

    class _RecordingPurger:
        async def handle(self, subscription, data):
            leader_calls.append(data)

        async def sync_scopes(self, *a, **k):
            return None

        def signal_stop(self):
            return None

        async def stop(self):
            return None

    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    purger = _RecordingPurger()
    t._pubsub_endpoint = endpoint
    t._purger = purger
    t._service = purger
    t._tasks = []
    t._webhook_tasks = []
    t._purger_sub_id = None

    await t.start()
    await t.stop()

    # The leader's own subscription is gone...
    await endpoint.publish(
        [opal_server_config.SCOPES_PURGE_CHANNEL], _purge_cmd(sid, False)
    )
    assert leader_calls == [], "leader purge handler still subscribed after stop()"

    # ...but the every-worker cache purge still works.
    await endpoint.publish(
        [opal_server_config.SCOPES_PURGE_CHANNEL], _purge_cmd(sid, True)
    )
    assert (
        cached_path not in GitPolicyFetcher.repos
    ), "stop() also unsubscribed the every-worker purge handler"


@pytest.mark.asyncio
async def test_stop_cancels_lock_holders_before_draining_purges(
    tmp_path, monkeypatch, _clean_fetcher_caches
):
    """Order matters: a queued purge's first act is to take lock_source, held by
    a sync across a whole clone/fetch (unbounded when SCOPES_GIT_FETCH_TIMEOUT
    is 0). Draining before super().stop() waits on a lock whose release requires
    that very cancellation — shutdown hangs, still holding the leadership lock,
    until k8s SIGKILLs the pod.

    The drained purge's observable completion is the confirmation it publishes
    (the leader no longer mutates the clone tree — that is the DELETE-serving
    worker's floor, and distributed disk reclaim is PER-15612).

    Mutation: awaiting the drain before super().stop() must fail here (it blocks
    for the whole _PURGE_DRAIN_TIMEOUT, past this wait_for).
    """
    from opal_server.git_fetcher import GitPolicyFetcher
    from opal_server.scopes.purge import LeaderScopePurger

    class _EmptyStore:
        async def all(self):
            return []

    class _RecordingPubSub:
        def __init__(self):
            self.published = []

        async def publish(self, topics, data=None):
            self.published.append(data)

    dead_dir = GitPolicyFetcher.base_dir(tmp_path) / ("c" * 64 + "-0")
    dead_dir.mkdir(parents=True)
    sid = dead_dir.name

    pubsub = _RecordingPubSub()
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=_EmptyStore(), pubsub_endpoint=pubsub
    )

    holding = asyncio.Event()

    async def _stuck_sync():
        async with GitPolicyFetcher.lock_source(sid):
            holding.set()
            await asyncio.sleep(3600)  # a fetch against a black-holed remote

    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    t._pubsub_endpoint = _FakeEndpoint()
    t._purger = purger
    t._service = purger
    t._tasks = [asyncio.create_task(_stuck_sync())]
    t._webhook_tasks = []
    t._purger_sub_id = None

    await holding.wait()
    await purger.handle(None, _purge_cmd(sid, False))  # queues behind the lock
    for _ in range(5):
        await asyncio.sleep(0)
    assert not pubsub.published, "purge should still be blocked on the held lock"

    await asyncio.wait_for(t.stop(), timeout=2)

    assert [
        d for d in pubsub.published if d.get("confirmed")
    ], "the drained purge never completed"


@pytest.mark.asyncio
async def test_stop_is_idempotent(monkeypatch):
    """Stop() runs twice on the normal path — BasePolicyWatcherTask.__aexit__
    and stop_server_background_tasks both call it — so the second pass must be
    a clean no-op (the old comment claimed it ran exactly once)."""
    from opal_server.config import opal_server_config
    from opal_server.policy.watcher.task import BasePolicyWatcherTask

    async def _noop_start(self):
        return None

    monkeypatch.setattr(BasePolicyWatcherTask, "start", _noop_start)
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)

    stops = []

    class _Purger:
        async def handle(self, *a, **k):
            return None

        def signal_stop(self):
            return None

        async def stop(self):
            stops.append("purger")

    class _Service:
        async def sync_scopes(self, *a, **k):
            return None

        async def stop(self):
            stops.append("service")

    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    purger = _Purger()
    t._pubsub_endpoint = _FakeEndpoint()
    t._purger = purger
    t._service = _Service()
    t._tasks = []
    t._webhook_tasks = []
    t._purger_sub_id = None

    await t.start()
    sub_id = t._purger_sub_id
    await t.stop()
    await t.stop()  # must not raise, must not unsubscribe twice

    assert t._pubsub_endpoint.notifier.unsubs == [
        (sub_id, [opal_server_config.SCOPES_PURGE_CHANNEL])
    ]
    # Only the purger is drained here, on every stop(). The DELETE floor's
    # drain is deliberately NOT the watcher's job — the floor's tasks live on
    # the ScopesService init_scope_router received, and the watcher exists only
    # on the leader while a DELETE usually lands on a non-leader. That drain is
    # pinned by test_shutdown_drains_the_routers_scopes_service.
    assert stops == ["purger", "purger"]


# --- Round-6 review: splitting the orphan sweep out deleted six tests here,
# three of which each carried a SECOND assertion about task.py code that
# survives. Those halves are restored below, sweep-free. ---


@pytest.mark.asyncio
async def test_periodic_polling_starts_when_enabled(monkeypatch):
    """The polling timer is the leader's only re-sync of scope repos outside
    webhooks and refresh-all.

    Mutation: dropping `if POLICY_REFRESH_INTERVAL > 0: create_task(
    self._periodic_polling())` from start() must fail here. Nothing else covers
    it — the git-leak bed runs with OPAL_POLICY_REFRESH_INTERVAL=0, so it never
    starts the task either.
    """
    from opal_server.config import opal_server_config
    from opal_server.policy.watcher.task import BasePolicyWatcherTask

    async def _noop_start(self):
        return None

    monkeypatch.setattr(BasePolicyWatcherTask, "start", _noop_start)
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 30)

    events = []
    rec = _Recorder(events)
    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    t._pubsub_endpoint = _FakeEndpoint()
    t._purger = rec
    t._service = rec
    t._tasks = []
    t._purger_sub_id = None

    await t.start()
    try:
        running = {task.get_coro().__name__ for task in t._tasks}
        assert "_periodic_polling" in running, running
    finally:
        for task in t._tasks:
            task.cancel()
        await asyncio.gather(*t._tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_sync_all_survives_a_raising_sync():
    """_sync_all is launched fire-and-forget from start(), so an unhandled
    raise dies silently: stop() gathers with return_exceptions=True and
    discards it, so not even asyncio's "never retrieved" warning fires until
    GC. The five-line comment above the try/except in task.py says exactly
    this; this is what enforces it.

    Mutation: stripping the try/except around `await self._service.sync_scopes()`
    must fail here.
    """
    events = []
    await _bare_task(events, fail_sync=True)._sync_all()  # must not raise
    assert events == ["sync"]


@pytest.mark.asyncio
async def test_refresh_all_trigger_syncs():
    """Trigger() with no scope_id is the refresh-all path.

    Mutation: replacing `await self._sync_all()` in trigger's else-branch must
    fail here.
    """
    events = []
    await _bare_task(events).trigger(topic=None, data=None)
    assert events == ["sync"]
