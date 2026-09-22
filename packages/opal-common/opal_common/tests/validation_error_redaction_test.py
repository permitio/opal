"""422 responses must not echo the rejected request body back to the caller.

From pydantic v2 every validation error carries an ``input`` key holding the
offending value, and FastAPI's default handler serializes ``exc.errors()``
wholesale - so a malformed body posted to a credential-bearing route came back
with its ``Authorization`` header or git deploy key intact, and landed in every
proxy log and APM trace in front of it.
"""

import json
from typing import List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.middleware import register_request_validation_exception_handler
from pydantic import BaseModel

SECRET = "Bearer super-secret-token-value-123"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjE=\n"


class _Config(BaseModel):
    headers: Optional[dict] = None


class _Entry(BaseModel):
    url: str
    config: Optional[dict] = None
    topics: List[str] = ["policy_data"]


class _Update(BaseModel):
    entries: List[_Entry]
    reason: str = ""


def _client(sanitized: bool) -> TestClient:
    app = FastAPI()
    if sanitized:
        register_request_validation_exception_handler(app)

    @app.post("/data/config")
    async def publish(update: _Update):  # pragma: no cover - body never runs on 422
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "body,secret",
    [
        # missing `url` on an entry that carries a fetcher Authorization header
        (
            {
                "entries": [{"config": {"headers": {"Authorization": SECRET}}}],
                "reason": "r",
            },
            SECRET,
        ),
        # a git deploy key in the rejected body
        (
            {
                "entries": [{"config": {"private_key": PRIVATE_KEY}}],
                "reason": "r",
            },
            PRIVATE_KEY,
        ),
        # wrong type rather than a missing field
        (
            {"entries": {"config": {"headers": {"Authorization": SECRET}}}},
            SECRET,
        ),
    ],
)
def test_422_does_not_echo_credentials(body, secret):
    response = _client(sanitized=True).post("/data/config", json=body)

    assert response.status_code == 422
    assert secret not in json.dumps(response.json())


def test_422_preserves_the_useful_error_fields():
    response = _client(sanitized=True).post(
        "/data/config",
        json={"entries": [{"config": {"headers": {"Authorization": SECRET}}}]},
    )

    detail = response.json()["detail"]
    assert detail and all({"loc", "msg", "type"} <= set(e) for e in detail)
    assert all(key not in error for error in detail for key in ("input", "ctx", "url"))
    assert ["body", "entries", 0, "url"] in [e["loc"] for e in detail]


def test_valid_body_still_reaches_the_endpoint():
    response = _client(sanitized=True).post(
        "/data/config",
        json={"entries": [{"url": "http://example.com"}], "reason": "r"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_unsanitized_app_would_leak_the_credential():
    """Pins the behaviour the handler exists to prevent."""
    response = _client(sanitized=False).post(
        "/data/config",
        json={"entries": [{"config": {"headers": {"Authorization": SECRET}}}]},
    )

    assert response.status_code == 422
    assert SECRET in json.dumps(response.json())
