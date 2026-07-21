"""preload_scopes() wiring: the gunicorn master must reset the fetcher
caches right after clearing git-executor bookkeeping, so forked workers
inherit neither (fix P).

A non-leader worker never populates GitPolicyFetcher.repos itself (sync,
the only writer, is leader-only) — its only entries would be ones inherited
from the master's preload fork. Since the fleet-wide purge broadcast only
reaches a worker whose broadcaster reader is running, a client-less
non-leader worker could never drop an inherited handle. Clearing the caches
in the master before fork means workers start (and stay) empty.
"""
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

    task_module.ScopesPolicyWatcherTask.preload_scopes()

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
