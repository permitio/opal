"""PUT /scopes re-pointing a scope to a new URL/branch must broadcast a purge
for the OLD source — otherwise its clone + cache entries orphan (bed gate:

test_scope_repoint_releases_old_repo_cache).
"""
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

    async def put(self, scope):
        self._scopes[scope.scope_id] = scope

    async def delete(self, scope_id):
        self._scopes.pop(scope_id, None)


class FakePubSubEndpoint:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        topics = topics if isinstance(topics, list) else [topics]
        self.published.append((topics, data))


class FakeAuthenticator:
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


def _client(repo, pubsub, base_dir):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=pubsub)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )
    return TestClient(app)


def _purge_messages(pubsub):
    return [
        (t, d)
        for (t, d) in pubsub.published
        if t == [opal_server_config.SCOPES_PURGE_CHANNEL]
    ]


def test_repoint_publishes_purge_for_old_source(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    old = _scope("s1", "https://git/old.git")
    repo = FakeScopeRepository([old])
    pubsub = FakePubSubEndpoint()
    client = _client(repo, pubsub, tmp_path)

    new = _scope("s1", "https://git/new.git")
    resp = client.put("/scopes", json=new.dict())

    assert resp.status_code == 201
    old_sid = GitPolicyFetcher.source_id(old.policy)
    old_clone = str(GitPolicyFetcher.repo_clone_path(tmp_path, old.policy))
    purges = _purge_messages(pubsub)
    assert len(purges) == 1
    _, payload = purges[0]
    assert payload == {
        "source_id": old_sid,
        "clone_path": old_clone,
        "scope_id": "s1",
        "reason": "repoint",
        "confirmed": False,
    }


def test_put_same_source_publishes_no_purge(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    old = _scope("s1", "https://git/same.git")
    repo = FakeScopeRepository([old])
    pubsub = FakePubSubEndpoint()
    client = _client(repo, pubsub, tmp_path)

    resp = client.put("/scopes", json=_scope("s1", "https://git/same.git").dict())

    assert resp.status_code == 201
    assert _purge_messages(pubsub) == []


def test_put_new_scope_publishes_no_purge(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    repo = FakeScopeRepository([])
    pubsub = FakePubSubEndpoint()
    client = _client(repo, pubsub, tmp_path)

    resp = client.put("/scopes", json=_scope("brand-new", "https://git/x.git").dict())

    assert resp.status_code == 201
    assert _purge_messages(pubsub) == []


class _AmbiguousPutRepository(FakeScopeRepository):
    """Put() commits server-side but the client sees an error."""

    async def put(self, scope):
        await super().put(scope)
        raise ConnectionError("connection dropped after the put committed")


def test_repoint_purge_still_publishes_when_put_raises_ambiguously(
    tmp_path, monkeypatch
):
    """A retry after an ambiguous PUT sees old_source_id == new_source_id
    already (the store was updated) and would never re-trigger the repoint
    purge on its own — the purge must fire from this same call, mirroring
    delete_scope's try/finally.

    The error still propagates to the client.
    """
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    old = _scope("s1", "https://git/old.git")
    repo = _AmbiguousPutRepository([old])
    pubsub = FakePubSubEndpoint()
    client = _client(repo, pubsub, tmp_path)

    new = _scope("s1", "https://git/new.git")
    with pytest.raises(ConnectionError):
        client.put("/scopes", json=new.dict())

    old_sid = GitPolicyFetcher.source_id(old.policy)
    old_clone = str(GitPolicyFetcher.repo_clone_path(tmp_path, old.policy))
    purges = _purge_messages(pubsub)
    assert len(purges) == 1
    _, payload = purges[0]
    assert payload == {
        "source_id": old_sid,
        "clone_path": old_clone,
        "scope_id": "s1",
        "reason": "repoint",
        "confirmed": False,
    }


def test_put_with_unreadable_old_record_still_succeeds(tmp_path, monkeypatch):
    """A corrupted/unreadable prior record must not 500 the PUT that overwrites
    it; the purge is skipped, and the old clone dir then stays on disk until
    PER-15612's sweep lands (nothing else will name that source)."""
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    class CorruptedReadRepository(FakeScopeRepository):
        async def get(self, scope_id):
            raise RuntimeError("stored record failed to parse")

    repo = CorruptedReadRepository([])
    pubsub = FakePubSubEndpoint()
    client = _client(repo, pubsub, tmp_path)

    resp = client.put("/scopes", json=_scope("s1", "https://git/new.git").dict())

    assert resp.status_code == 201
    assert _purge_messages(pubsub) == []
