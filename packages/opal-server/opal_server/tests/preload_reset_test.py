"""preload_scopes() wiring: the gunicorn master must reset the fetcher caches
right after clearing git-executor bookkeeping, so forked workers inherit
neither (fix P).

A non-leader worker never populates GitPolicyFetcher.repos itself (sync,
the only writer, is leader-only) — its only entries would be ones
inherited from the master's preload fork. Since the fleet-wide purge
broadcast only reaches a worker whose broadcaster reader is running, a
client-less non-leader worker could never drop an inherited handle.
Clearing the caches in the master before fork means workers start (and
stay) empty.
"""
import asyncio

import opal_server.scopes.task as task_module
from opal_server.config import opal_server_config


def test_preload_scopes_resets_fetcher_caches_after_shutdown(monkeypatch):
    events = []

    class _StubService:
        def __init__(self, *args, **kwargs):
            pass

        async def sync_scopes(self, *args, **kwargs):
            events.append("sync_scopes")

    def _stub_shutdown_git_executor():
        events.append("shutdown_git_executor")

    class _StubGitPolicyFetcher:
        @staticmethod
        def reset_caches():
            events.append("reset_caches")

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(
        task_module, "shutdown_git_executor", _stub_shutdown_git_executor
    )
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGitPolicyFetcher)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    try:
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        # preload_scopes runs asyncio.run(), which closes its loop and leaves
        # the main thread with no current event loop. On Python 3.9 a later
        # sync test that constructs an asyncio primitive (e.g. asyncio.Lock())
        # then raises "no current event loop" — a cross-test poisoning that
        # only bites 3.9 (3.10+ primitives don't grab the loop at __init__).
        # Restore a fresh loop so test isolation holds.
        asyncio.set_event_loop(asyncio.new_event_loop())

    assert events == ["sync_scopes", "shutdown_git_executor", "reset_caches"], events


def test_preload_scopes_noop_when_scopes_disabled(monkeypatch):
    """Guards the ordering test's premise: with SCOPES off, nothing in the
    block (including reset_caches) should run at all."""
    events = []

    class _StubGitPolicyFetcher:
        @staticmethod
        def reset_caches():
            events.append("reset_caches")

    monkeypatch.setattr(
        task_module, "shutdown_git_executor", lambda: events.append("shutdown")
    )
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGitPolicyFetcher)
    monkeypatch.setattr(opal_server_config, "SCOPES", False)

    task_module.ScopesPolicyWatcherTask.preload_scopes()

    assert events == []


def test_preload_scopes_drains_before_teardown(monkeypatch):
    events = []

    class _StubService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            events.append("sync_scopes")

    class _StubGPF:
        @staticmethod
        def reset_caches():
            events.append("reset_caches")

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(
        task_module, "drain_git_ops", lambda t: events.append("drain") or True
    )
    monkeypatch.setattr(
        task_module, "shutdown_git_executor", lambda: events.append("shutdown")
    )
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGPF)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    try:
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())
    assert events == ["sync_scopes", "drain", "shutdown", "reset_caches"], events


def test_preload_warns_when_the_drain_times_out_with_ops_still_in_flight(monkeypatch):
    """A drain that times out means git threads survive into the forked
    workers, where they can race a worker on the shared clone dir.

    That is the one condition carrying this risk, and the warning is its
    only signal — nothing else reports it, and reset_caches deliberately
    skips those handles rather than failing loudly. Mutation: drop the
    `if not drained` warning and the whole condition becomes invisible.
    """
    from opal_common.logger import logger as opal_logger

    class _StubService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            return None

    class _StubGPF:
        @staticmethod
        def reset_caches():
            return None

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda t: False)  # timed out
    monkeypatch.setattr(task_module, "git_busy_count", lambda: 3)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGPF)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        opal_logger.remove(sink)
        asyncio.set_event_loop(asyncio.new_event_loop())

    warned = [r for r in records if "Preload drain timed out" in r]
    assert warned, f"a timed-out drain was not reported at all: {records}"
    # Against the RENDERED payload, not the formatted record: a bare "3" is
    # supplied by the timestamp and the source line number, so `"3" in record`
    # holds for any drain warning at all and cannot fail.
    assert (
        "in flight (3)" in warned[0]
    ), f"the in-flight count is missing from the warning: {warned[0]}"


def test_preload_does_not_warn_when_the_drain_succeeds(monkeypatch):
    """The inverse, so the test above cannot pass by always-warning."""
    from opal_common.logger import logger as opal_logger

    class _StubService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            return None

    class _StubGPF:
        @staticmethod
        def reset_caches():
            return None

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda t: True)  # drained
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGPF)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        opal_logger.remove(sink)
        asyncio.set_event_loop(asyncio.new_event_loop())

    assert not [
        r for r in records if "Preload drain timed out" in r
    ], f"warned on a clean drain: {records}"
