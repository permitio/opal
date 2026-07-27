"""GET /scopes/{scope_id}/policy when the clone dir vanishes.

Record missing -> default scope bundle (unchanged contract). Record
PRESENT but the clone is transiently broken -> 503 + Retry-After: a live
tenant must never be served another tenant's policy (PR3 flip of the
PR2-era regression lock).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from git import NoSuchPathError
from opal_common.schemas.policy import PolicyBundle
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


def _default_bundle():
    return PolicyBundle(
        manifest=[], hash="default-head", data_modules=[], policy_modules=[]
    )


def test_live_scope_clone_vanish_returns_retryable_503(tmp_path, monkeypatch):
    live = _scope("live", "https://git/live.git")
    default = _scope("default", "https://git/default.git")
    repo = FakeScopeRepository([live, default])

    def fake_make_bundle(self, base_hash):
        if self._scope_id == "live":
            raise NoSuchPathError(str(tmp_path / "gone"))
        return _default_bundle()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/live/policy")

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"


def test_live_scope_oserror_returns_retryable_503(tmp_path, monkeypatch):
    """make_bundle's tree-walk can raise raw OSError if the dir vanishes mid-
    walk — an unhandled 500 before PR3."""
    live = _scope("live", "https://git/live.git")
    repo = FakeScopeRepository([live])

    def fake_make_bundle(self, base_hash):
        raise OSError(2, "No such file or directory")

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/live/policy")

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"


def test_missing_scope_still_falls_back_to_default_bundle(tmp_path, monkeypatch):
    """The record-missing fallback is the contract — unchanged."""
    default = _scope("default", "https://git/default.git")
    repo = FakeScopeRepository([default])

    monkeypatch.setattr(
        GitPolicyFetcher, "make_bundle", lambda self, base_hash: _default_bundle()
    )
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/ghost/policy")

    assert resp.status_code == 200
    assert resp.json()["hash"] == "default-head"


from opal_server.git_fetcher import BranchHeadNotFoundError


def test_wrong_branch_returns_non_retryable_409(tmp_path, monkeypatch):
    live = _scope("live", "https://git/live.git", branch="does-not-exist")
    repo = FakeScopeRepository([live])

    def fake_make_bundle(self, base_hash):
        raise BranchHeadNotFoundError("Could not find current branch head")

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr("opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path))
    resp = _client(repo, tmp_path).get("/scopes/live/policy")
    assert resp.status_code == 409
    assert "retry-after" not in resp.headers
