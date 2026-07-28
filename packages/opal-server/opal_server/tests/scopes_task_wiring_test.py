"""ScopesPolicyWatcherTask wiring: sync-then-sweep ordering on the boot and
refresh-all paths (the bed's orphan gates depend on the trigger path
sweeping; unit-pins the wiring so a refactor can't silently drop it)."""
import asyncio

import pytest
from opal_server.scopes.task import ScopesPolicyWatcherTask


class _Recorder:
    def __init__(self, events, fail_sweep=False, fail_sync=False):
        self._events = events
        self._fail_sweep = fail_sweep
        self._fail_sync = fail_sync

    async def sync_scopes(self, *args, **kwargs):
        self._events.append("sync")
        if self._fail_sync:
            raise RuntimeError("store scan failed")

    async def sync_scope(self, *args, **kwargs):
        self._events.append("sync_one")

    async def sweep_orphans(self):
        self._events.append("sweep")
        if self._fail_sweep:
            raise PermissionError("disk broke")


def _bare_task(events, fail_sweep=False, fail_sync=False):
    """Construct without __init__ (it needs Redis); wire only what the methods
    under test use."""
    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    rec = _Recorder(events, fail_sweep=fail_sweep, fail_sync=fail_sync)
    t._service = rec
    t._purger = rec
    return t


@pytest.mark.asyncio
async def test_sync_all_then_sweep_runs_in_order():
    events = []
    await _bare_task(events)._sync_all_then_sweep()
    assert events == ["sync", "sweep"]


@pytest.mark.asyncio
async def test_sweep_failure_is_swallowed_and_does_not_mask_sync():
    events = []
    await _bare_task(events, fail_sweep=True)._sync_all_then_sweep()  # no raise
    assert events == ["sync", "sweep"]


@pytest.mark.asyncio
async def test_sweep_failure_is_logged():
    """Swallowing the sweep failure must not make it invisible — boot-time
    sweep failures need to surface somewhere an operator can find them."""
    from opal_common.logger import logger as opal_logger

    events = []
    records = []
    sink_id = opal_logger.add(lambda m: records.append(str(m)), level="ERROR")
    try:
        await _bare_task(events, fail_sweep=True)._sync_all_then_sweep()
    finally:
        opal_logger.remove(sink_id)

    assert any("Orphan sweep failed" in r for r in records), f"not logged: {records}"


@pytest.mark.asyncio
async def test_refresh_all_trigger_sweeps():
    events = []
    await _bare_task(events).trigger(topic=None, data=None)
    assert events == ["sync", "sweep"]


@pytest.mark.asyncio
async def test_single_scope_trigger_does_not_sweep():
    events = []
    await _bare_task(events).trigger(topic=None, data={"scope_id": "s1"})
    assert events == ["sync_one"]


@pytest.mark.asyncio
async def test_periodic_orphan_sweep_runs_with_polling_disabled(monkeypatch):
    from opal_server.config import opal_server_config

    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)
    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_INTERVAL", 300)
    calls = {"n": 0}

    async def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    events = []
    with pytest.raises(asyncio.CancelledError):
        await _bare_task(events)._periodic_orphan_sweep()
    assert events.count("sweep") == 1
    assert "sync" not in events


@pytest.mark.asyncio
async def test_periodic_polling_syncs_but_does_not_sweep(monkeypatch):
    # Polling must NOT sweep: the always-on _periodic_orphan_sweep owns that,
    # independent of POLICY_REFRESH_INTERVAL (per the config docs). Sweeping here
    # too would double the disk scans and confirmed-orphan purge broadcasts.
    from opal_server.config import opal_server_config

    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0.001)
    events = []
    task = asyncio.create_task(_bare_task(events)._periodic_polling())
    try:
        while events.count("sync") < 2:
            await asyncio.sleep(0)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert "sweep" not in events


@pytest.mark.asyncio
async def test_periodic_polling_survives_a_raising_sync(monkeypatch):
    # A raising sync_scopes in a poll pass must be caught (logged) and the loop
    # kept alive — one store hiccup must not kill periodic sync.
    from opal_server.config import opal_server_config

    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0.001)
    events = []
    task = asyncio.create_task(_bare_task(events, fail_sync=True)._periodic_polling())
    try:
        while events.count("sync") < 2:
            await asyncio.sleep(0)
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
            self.subs = []

        async def subscribe(self, topics, callback):
            self.subs.append((list(topics), callback))

    class FakePurger:
        async def handle(self, *a, **k):
            return None

        async def sweep_orphans(self):
            return None

    class FakeService:
        async def sync_scopes(self, *a, **k):
            return None

    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    t._pubsub_endpoint = FakeEndpoint()
    t._purger = FakePurger()
    t._service = FakeService()
    t._tasks = []
    await t.start()
    try:
        assert t._pubsub_endpoint.subs == [
            ([opal_server_config.SCOPES_PURGE_CHANNEL], t._purger.handle)
        ]
    finally:
        for task in t._tasks:
            task.cancel()
        await asyncio.gather(*t._tasks, return_exceptions=True)
