import asyncio

import pytest

from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.schemas.scopes import Scope
from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService


class _FakeRepoStore:
    def __init__(self, scopes):
        self._s = {x.scope_id: x for x in scopes}

    async def get(self, sid):
        if sid not in self._s:
            raise ScopeNotFoundError(sid)
        return self._s[sid]

    async def all(self):
        return list(self._s.values())

    async def delete(self, sid):
        self._s.pop(sid, None)


def _git_scope(sid, url):
    return Scope(
        scope_id=sid,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=url,
            branch="main",
            auth={"auth_type": "none"},
        ),
        data={"entries": []},
    )


def test_sync_concurrency_default():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_SYNC_CONCURRENCY == 10


@pytest.mark.asyncio
async def test_source_lock_is_stable_per_source(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repo_locks", {})
    lock_a1 = GitPolicyFetcher.source_lock("src-a")
    lock_a2 = GitPolicyFetcher.source_lock("src-a")
    lock_b = GitPolicyFetcher.source_lock("src-b")
    assert lock_a1 is lock_a2  # same source -> same lock object
    assert lock_a1 is not lock_b
    assert isinstance(lock_a1, asyncio.Lock)


@pytest.mark.asyncio
async def test_delete_waits_for_in_flight_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repo_locks", {})
    monkeypatch.setattr(GitPolicyFetcher, "repos", {})
    monkeypatch.setattr(GitPolicyFetcher, "repos_last_fetched", {})
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree", lambda *a, **k: None
    )

    scope = _git_scope("s1", "https://git/repo.git")
    svc = ScopesService(
        base_dir=tmp_path, scopes=_FakeRepoStore([scope]), pubsub_endpoint=None
    )
    sid = GitPolicyFetcher.source_id(scope.policy)

    # simulate an in-flight fetch holding the per-source lock
    lock = GitPolicyFetcher.source_lock(sid)
    await lock.acquire()

    delete_task = asyncio.create_task(svc.delete_scope("s1"))
    await asyncio.sleep(0.05)
    assert not delete_task.done(), "delete proceeded while the source lock was held"

    lock.release()
    await asyncio.wait_for(delete_task, timeout=2)
    assert delete_task.done()
