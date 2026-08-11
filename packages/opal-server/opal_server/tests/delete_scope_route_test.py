import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())

    async def delete(self, scope_id):
        self._scopes.pop(scope_id, None)


class FakeAuthenticator:
    """Mimics a JWTAuthenticator whose verifier is disabled (no public key)."""

    enabled = False

    def __call__(self):
        return {}


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


def _client(repo, base_dir, pubsub=None):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=pubsub)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_caches():
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    yield
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()


def test_delete_route_deletes_the_record_without_pubsub(tmp_path):
    """DELETE /scopes/{id} must flow through ScopesService.delete_scope and
    delete the record even with no pubsub endpoint wired (degraded mode).

    Cache purging is two-phase fleet-wide (the leader's sibling-checked
    confirmation drains every worker) plus a best-effort LOCAL floor
    that delete_scope spawns for the serving worker. The floor is
    deliberately backgrounded, and TestClient tears its loop down at the
    end of the request, so asserting on the caches from here would be a
    coin flip in either direction. Its effect is pinned
    deterministically instead, by delete_scope_cache_purge_test's floor
    tests, which drain the task.
    """
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])

    resp = _client(repo, tmp_path).delete("/scopes/only")

    assert resp.status_code == 204
    assert "only" not in repo._scopes  # record deleted


def test_delete_route_missing_scope_stays_204(tmp_path):
    """Deleting a nonexistent scope was a silent no-op (204) before the purge
    wiring and must remain one."""
    resp = _client(FakeScopeRepository([]), tmp_path).delete("/scopes/ghost")
    assert resp.status_code == 204


class FakePubSubEndpoint:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((list(topics), data))


def test_delete_route_publishes_purge_request(tmp_path):
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    pubsub = FakePubSubEndpoint()
    sid = GitPolicyFetcher.source_id(scope.policy)
    resp = _client(repo, tmp_path, pubsub=pubsub).delete("/scopes/only")
    assert resp.status_code == 204
    assert "only" not in repo._scopes
    assert len(pubsub.published) == 1
    topics, payload = pubsub.published[0]
    assert topics == [opal_server_config.SCOPES_PURGE_CHANNEL]
    assert payload["source_id"] == sid and payload["scope_id"] == "only"
    assert payload["reason"] == "delete" and payload["confirmed"] is False
