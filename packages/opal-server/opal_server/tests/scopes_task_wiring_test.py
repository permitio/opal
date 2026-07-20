"""ScopesPolicyWatcherTask wiring: sync-then-sweep ordering on the boot and
refresh-all paths (the bed's orphan gates depend on the trigger path
sweeping; unit-pins the wiring so a refactor can't silently drop it)."""
import asyncio

import pytest
from opal_server.scopes.task import ScopesPolicyWatcherTask


class _Recorder:
    def __init__(self, events, fail_sweep=False):
        self._events = events
        self._fail_sweep = fail_sweep

    async def sync_scopes(self, *args, **kwargs):
        self._events.append("sync")

    async def sync_scope(self, *args, **kwargs):
        self._events.append("sync_one")

    async def sweep_orphans(self):
        self._events.append("sweep")
        if self._fail_sweep:
            raise PermissionError("disk broke")


def _bare_task(events, fail_sweep=False):
    """Construct without __init__ (it needs Redis); wire only what the methods
    under test use."""
    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    rec = _Recorder(events, fail_sweep=fail_sweep)
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
async def test_refresh_all_trigger_sweeps():
    events = []
    await _bare_task(events).trigger(topic=None, data=None)
    assert events == ["sync", "sweep"]


@pytest.mark.asyncio
async def test_single_scope_trigger_does_not_sweep():
    events = []
    await _bare_task(events).trigger(topic=None, data={"scope_id": "s1"})
    assert events == ["sync_one"]
