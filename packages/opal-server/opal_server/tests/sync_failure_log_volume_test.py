"""P6 (PR3 fixes): a failed scope sync is ONE error line, not a traceback.

With dozens of broken sources every pass logged
``Could not fetch policy for scope ...`` WITH a ~40-line traceback per source:
the container log rotated (10 MiB) within minutes of a boot and the boot
markers were gone; in prod the same mechanism made opal-server the largest log
producer in the org. The rule now: ERROR names the scope, remote and reason
without a traceback; the traceback is emitted at DEBUG only.
"""
import asyncio
from pathlib import Path

import pytest
from loguru import logger
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.scopes import service as service_module
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


class _ExplodingFetcher:
    """Stands in for GitPolicyFetcher: the sync raises the way a broken remote
    with a bad credential type does (an exception the clone path does not
    swallow itself)."""

    calls = 0

    def __init__(self, *a, **k):
        pass

    @staticmethod
    def source_id(source):
        return "src-1"

    async def fetch_and_notify_on_changes(self, **kwargs):
        _ExplodingFetcher.calls += 1
        raise ValueError("invalid credential type")


def _scope(scope_id, url="http://broken.invalid/repo.git"):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch="main", auth=NoAuthData(auth_type="none")
        ),
        data={"entries": []},
    )


@pytest.fixture
def captured_logs():
    """Capture loguru RECORDS at DEBUG: each carries its level, message and
    whether an exception (traceback) is attached — which is exactly the
    property under test, and one that a text sink cannot attribute reliably."""
    records = []
    sink_id = logger.add(lambda m: records.append(m.record), level="DEBUG")
    yield records
    logger.remove(sink_id)


def _errors(records):
    return [r for r in records if r["level"].name == "ERROR"]


def _debug_tracebacks(records):
    return [r for r in records if r["level"].name == "DEBUG" and r["exception"] is not None]


@pytest.mark.asyncio
async def test_failed_sync_logs_one_error_line_without_a_traceback(monkeypatch, tmp_path, captured_logs):
    monkeypatch.setattr(service_module, "GitPolicyFetcher", _ExplodingFetcher)
    service = ScopesService(
        base_dir=Path(tmp_path), scopes=FakeScopeRepository([_scope("gitops-http401-0")]), pubsub_endpoint=None
    )

    await service.sync_scope(scope_id="gitops-http401-0", notify_on_changes=False)
    await service.sync_scope(scope_id="gitops-http401-0", notify_on_changes=False)

    errors = _errors(captured_logs)
    assert len(errors) == 2, [r["message"] for r in captured_logs]  # one per failed sync, nothing extra
    for r in errors:
        msg = r["message"]
        assert "gitops-http401-0" in msg and "broken.invalid" in msg, msg
        assert "ValueError" in msg and "invalid credential type" in msg, msg
        # The traceback is NOT on the ERROR record...
        assert r["exception"] is None, "ERROR record carries a traceback again — the log firehose is back"
    # ...it is available at DEBUG for anyone chasing that source.
    tb = _debug_tracebacks(captured_logs)
    assert len(tb) == 2 and all("gitops-http401-0" in r["message"] for r in tb), [r["message"] for r in tb]


@pytest.mark.asyncio
async def test_sync_scopes_pass_wrapper_also_stays_traceback_free(monkeypatch, tmp_path, captured_logs):
    """The per-pass wrapper (_sync_one) catches anything sync_scope lets
    escape; make it explode there and check the same rule holds."""
    async def _boom(self, *a, **k):
        raise RuntimeError("store hiccup")

    monkeypatch.setattr(ScopesService, "sync_scope", _boom)
    service = ScopesService(
        base_dir=Path(tmp_path), scopes=FakeScopeRepository([_scope("s1"), _scope("s2")]), pubsub_endpoint=None
    )
    await service.sync_scopes(notify_on_changes=False)
    errors = _errors(captured_logs)
    assert len(errors) == 2 and all("RuntimeError: store hiccup" in r["message"] for r in errors), [r["message"] for r in captured_logs]
    assert all(r["exception"] is None for r in errors)
    assert len(_debug_tracebacks(captured_logs)) == 2, "one DEBUG traceback per failure"
