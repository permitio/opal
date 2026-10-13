"""Scope route logs must redact a remote URL's auth carried in git errors.

The scope routes log the exception that failed a bundle build or a record
read. Git errors can quote the remote verbatim
(``https://user:pw@host/repo.git``), and loguru keeps bound kwargs in
``record["extra"]``, which a ``serialize=True`` sink prints as-is. Each case
checks a text sink and a ``serialize=True`` sink.
"""

from contextlib import contextmanager
from typing import Iterator, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.redaction_fixtures import capture_logs
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    BranchHeadNotFoundError,
    CloneNotPopulatedError,
    GitPolicyFetcher,
)
from opal_server.scopes import api as scopes_api_module
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

FAKE_KEY = "FAKE-KEY-123"
FAKE_REMOTE = f"https://fakeuser:{FAKE_KEY}@git.example.com/org/policy.git"
GIT_ERROR_TEXT = f"failed to fetch {FAKE_REMOTE}"


class FakeScopeRepository:
    def __init__(self, scopes, get_error=None):
        self._scopes = {s.scope_id: s for s in scopes}
        self._get_error = get_error

    async def get(self, scope_id):
        if self._get_error is not None:
            raise self._get_error
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def put(self, scope):
        self._scopes[scope.scope_id] = scope

    async def all(self):
        return list(self._scopes.values())


class FakeAuthenticator:
    """Mimics a JWTAuthenticator whose verifier is disabled (no public key)."""

    enabled = False

    def __call__(self):
        return {}


class FakePubSub:
    async def publish(self, topics, data=None):
        return None


@contextmanager
def _captured_logs() -> Iterator[Tuple[List[str], List[str]]]:
    with capture_logs() as logs:
        yield logs.text, logs.serialized


def _scope(scope_id):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=f"https://git.example.com/org/{scope_id}.git",
            auth=NoAuthData(),
        ),
    )


def _client(repo, base_dir):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=None)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), FakePubSub(), service),
        prefix="/scopes",
    )
    return TestClient(app)


def _assert_logged_and_redacted(text, serialized, fragment):
    matching = [line for line in serialized if fragment in line]
    assert matching, f"no log line containing {fragment!r}: {serialized}"
    assert "git.example.com/org/policy.git" in matching[0]
    for output in (text, serialized):
        assert FAKE_KEY not in "\n".join(output)


def _raise_always(error):
    def make_bundle(self, base_hash):
        raise error

    return make_bundle


def _not_populated_then(error):
    """First attempt: clone not populated yet; every later attempt: ``error``."""
    calls = []

    def make_bundle(self, base_hash):
        calls.append(base_hash)
        if len(calls) == 1:
            raise CloneNotPopulatedError("clone not populated")
        raise error

    return make_bundle


@pytest.fixture(autouse=True)
def _base_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0)


@pytest.mark.parametrize(
    "requested_scope,make_bundle,status_code,fragment",
    [
        (
            "live",
            _raise_always(BranchHeadNotFoundError(GIT_ERROR_TEXT)),
            409,
            "bundle unavailable",
        ),
        (
            "live",
            _raise_always(OSError(GIT_ERROR_TEXT)),
            503,
            "is live but its clone is unavailable",
        ),
        (
            "live",
            _raise_always(CloneNotPopulatedError(GIT_ERROR_TEXT)),
            503,
            "clone is not populated yet",
        ),
        (
            "missing",
            _raise_always(OSError(GIT_ERROR_TEXT)),
            503,
            "Default-scope bundle for missing is temporarily unavailable (",
        ),
        (
            "missing",
            _raise_always(CloneNotPopulatedError(GIT_ERROR_TEXT)),
            503,
            "temporarily unavailable after waiting",
        ),
    ],
    ids=[
        "branch_head_not_found",
        "clone_unavailable",
        "clone_not_populated",
        "default_scope_unavailable",
        "default_scope_not_populated",
    ],
)
def test_policy_bundle_error_logs_redact_remote_auth(
    tmp_path, monkeypatch, requested_scope, make_bundle, status_code, fragment
):
    repo = FakeScopeRepository([_scope("live"), _scope("default")])
    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", make_bundle)

    with _captured_logs() as (text, serialized):
        response = _client(repo, tmp_path).get(f"/scopes/{requested_scope}/policy")

    assert response.status_code == status_code
    _assert_logged_and_redacted(text, serialized, fragment)


def test_clone_wait_failure_log_redacts_remote_auth(tmp_path, monkeypatch):
    """The wait logs the exception that ended it when a later attempt fails for
    a reason other than the clone still being empty."""
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 5)
    monkeypatch.setattr(scopes_api_module, "_CLONE_WAIT_POLL_SECONDS", 0.01)
    monkeypatch.setattr(
        GitPolicyFetcher, "make_bundle", _not_populated_then(OSError(GIT_ERROR_TEXT))
    )
    repo = FakeScopeRepository([_scope("live")])

    with _captured_logs() as (text, serialized):
        response = _client(repo, tmp_path).get("/scopes/live/policy")

    assert response.status_code == 503
    _assert_logged_and_redacted(text, serialized, "before failing")


def test_put_scope_unreadable_previous_record_log_redacts_remote_auth(
    tmp_path,
):
    repo = FakeScopeRepository([], get_error=RuntimeError(GIT_ERROR_TEXT))

    with _captured_logs() as (text, serialized):
        response = _client(repo, tmp_path).put(
            "/scopes", json=_scope("live").model_dump()
        )

    assert response.status_code == 201
    _assert_logged_and_redacted(text, serialized, "skipping repoint purge")


def test_default_bundle_is_still_served_when_present(tmp_path, monkeypatch):
    """Guards the default-scope cases above: the fallback route is reached
    and succeeds when the default scope's bundle builds."""
    bundle = PolicyBundle(manifest=[], hash="h", data_modules=[], policy_modules=[])
    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", lambda self, base: bundle)
    repo = FakeScopeRepository([_scope("default")])

    response = _client(repo, tmp_path).get("/scopes/missing/policy")

    assert response.status_code == 200
    assert response.json()["hash"] == "h"
