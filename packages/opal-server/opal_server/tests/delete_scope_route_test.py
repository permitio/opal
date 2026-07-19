import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
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


def _client(repo, base_dir):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=None)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), None, service),
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


def test_delete_route_purges_fetcher_caches(tmp_path, monkeypatch):
    """DELETE /scopes/{id} must flow through ScopesService.delete_scope so the
    GitPolicyFetcher caches drain (the git-leak churn gate)."""
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])

    sid = GitPolicyFetcher.source_id(scope.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree", lambda *a, **k: None
    )

    resp = _client(repo, tmp_path).delete("/scopes/only")

    assert resp.status_code == 204
    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched


def test_delete_route_missing_scope_stays_204(tmp_path):
    """Deleting a nonexistent scope was a silent no-op (204) before the purge
    wiring and must remain one."""
    resp = _client(FakeScopeRepository([]), tmp_path).delete("/scopes/ghost")
    assert resp.status_code == 204
