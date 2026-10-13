"""The policy webhook must not return or log the auth embedded in the tracked
repo / bundle URL.

With no ``POLICY_REPO_WEBHOOK_SECRET`` configured (the default) the git webhook
route is unauthenticated, and it answers with the tracked ``repo_url``. A
``https://user:token@host/repo.git?token=...`` remote must come back (and be
logged) with the auth stripped.

Logs are checked through a ``serialize=True`` sink as well as a text sink:
loguru stores bound kwargs in ``record["extra"]``, which the JSON sink prints
verbatim and the message-only patcher in ``configure_logs`` never touches.
"""

from contextlib import contextmanager
from typing import Iterator, List, Tuple

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from opal_common.logger import logger
from opal_common.schemas.webhook import GitWebhookRequestParams
from opal_server.config import PolicySourceTypes, opal_server_config
from opal_server.policy.webhook.api import get_webhook_router
from opal_server.policy.webhook.deps import extracted_git_changes

FAKE_USERINFO = "fakeuser:FAKE-KEY-123"
FAKE_QUERY_TOKEN = "FAKE-QUERY-TOKEN-456"
FAKE_VALUES = ("FAKE-KEY-123", FAKE_QUERY_TOKEN, "fakeuser")

REPO_URL = (
    f"https://{FAKE_USERINFO}@git.example.com/org/policy.git?token={FAKE_QUERY_TOKEN}"
)
BUNDLE_URL = f"https://{FAKE_USERINFO}@bundles.example.com/bundle.tar.gz?token={FAKE_QUERY_TOKEN}"

GITHUB_PARAMS = GitWebhookRequestParams(
    secret_header_name="X-Hub-Signature-256",
    secret_type="signature",
    secret_parsing_regex="sha256=(.*)",
    event_header_name="X-GitHub-Event",
    push_event_value="push",
)


@contextmanager
def _captured_logs() -> Iterator[Tuple[List[str], List[str]]]:
    text: List[str] = []
    serialized: List[str] = []
    sink_ids = [
        logger.add(lambda m: text.append(str(m)), level="DEBUG"),
        logger.add(lambda m: serialized.append(str(m)), level="DEBUG", serialize=True),
    ]
    try:
        yield text, serialized
    finally:
        for sink_id in sink_ids:
            logger.remove(sink_id)


async def _no_publish(*args, **kwargs):
    return None


def _client(source_type, git_changes=Depends(extracted_git_changes)):
    app = FastAPI()
    app.include_router(
        get_webhook_router(
            [], git_changes, source_type, _no_publish, webhook_config=GITHUB_PARAMS
        )
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(opal_server_config, "POLICY_REPO_URL", REPO_URL)
    monkeypatch.setattr(opal_server_config, "POLICY_BUNDLE_URL", BUNDLE_URL)
    monkeypatch.setattr(opal_server_config, "POLICY_REPO_WEBHOOK_ENFORCE_BRANCH", False)


def _assert_absent(*outputs: str):
    for output in outputs:
        for value in FAKE_VALUES:
            assert value not in output, output


def test_ping_on_tracked_repo_returns_and_logs_redacted_url():
    body = {"repository": {"clone_url": "https://git.example.com/org/policy.git"}}

    with _captured_logs() as (text, serialized):
        response = _client(PolicySourceTypes.Git).post(
            "/webhook", json=body, headers={"X-GitHub-Event": "ping"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["repo_url"] == (
        "https://***@git.example.com/org/policy.git?token=***"
    )
    triggered = [line for line in serialized if "triggered webhook on repo" in line]
    assert triggered, serialized
    _assert_absent(response.text, "\n".join(text), "\n".join(serialized))


def test_webhook_for_other_repo_logs_redacted_url():
    body = {"repository": {"clone_url": "https://git.example.com/org/other.git"}}

    with _captured_logs() as (text, serialized):
        response = _client(PolicySourceTypes.Git).post(
            "/webhook", json=body, headers={"X-GitHub-Event": "push"}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    unexpected = [line for line in serialized if "unexpected webhook" in line]
    assert unexpected, serialized
    assert "git.example.com/org/policy.git" in unexpected[0]
    _assert_absent(response.text, "\n".join(text), "\n".join(serialized))


def test_api_source_webhook_returns_redacted_bundle_url():
    async def _no_changes():
        return None

    response = _client(PolicySourceTypes.Api, git_changes=Depends(_no_changes)).post(
        "/webhook"
    )

    assert response.status_code == 200
    assert response.json()["repo_url"] == (
        "https://***@bundles.example.com/bundle.tar.gz?token=***"
    )
    _assert_absent(response.text)
