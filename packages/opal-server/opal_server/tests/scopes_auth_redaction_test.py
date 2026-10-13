"""GET /scopes and GET /scopes/{id} must not return a scope's git auth.

Both routes declare ``response_model_exclude`` to drop ``policy.auth``. For the
list route the exclude has to address every item (``__all__``); a bare
``{"policy": {"auth"}}`` is silently ignored for a ``List[Scope]`` response
model, which returned every scope's token / password / SSH private key.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    NoAuthData,
    SSHAuthData,
    UserPassAuthData,
)
from opal_common.schemas.scopes import Scope
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

FAKE_TOKEN = "FAKE-KEY-123"
FAKE_PASSWORD = "fakepass-FAKE-456"
FAKE_PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE-PRIVATE-KEY-789\n"
    "-----END OPENSSH PRIVATE KEY-----"
)
FAKE_VALUES = (FAKE_TOKEN, FAKE_PASSWORD, FAKE_PRIVATE_KEY, "FAKE-PRIVATE-KEY-789")

AUTHS = {
    "token": GitHubTokenAuthData(token=FAKE_TOKEN),
    "userpass": UserPassAuthData(username="fakeuser", password=FAKE_PASSWORD),
    "ssh": SSHAuthData(username="git", private_key=FAKE_PRIVATE_KEY),
    "none": NoAuthData(),
}


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())


class FakeAuthenticator:
    """Mimics a JWTAuthenticator whose verifier is disabled (no public key)."""

    enabled = False

    def __call__(self):
        return {}


def _scope(scope_id, auth):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=f"https://git.example.com/org/{scope_id}.git",
            auth=auth,
        ),
    )


@pytest.fixture
def client(tmp_path):
    repo = FakeScopeRepository([_scope(name, auth) for name, auth in AUTHS.items()])
    service = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), None, service),
        prefix="/scopes",
    )
    return TestClient(app)


def _assert_no_auth(scope_json):
    assert "auth" not in scope_json["policy"], scope_json
    # The rest of the policy source is still returned.
    assert scope_json["policy"]["url"].startswith("https://git.example.com/org/")


def test_get_all_scopes_omits_policy_auth(client):
    response = client.get("/scopes")

    assert response.status_code == 200
    scopes = response.json()
    assert {s["scope_id"] for s in scopes} == set(AUTHS)
    for scope_json in scopes:
        _assert_no_auth(scope_json)
    for value in FAKE_VALUES:
        assert value not in response.text
        assert value not in json.dumps(scopes)


@pytest.mark.parametrize("scope_id", sorted(AUTHS))
def test_get_scope_omits_policy_auth(client, scope_id):
    response = client.get(f"/scopes/{scope_id}")

    assert response.status_code == 200
    _assert_no_auth(response.json())
    for value in FAKE_VALUES:
        assert value not in response.text
