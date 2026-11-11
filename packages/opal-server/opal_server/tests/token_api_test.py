"""POST /token reports the token's expiry as naive UTC (no offset), as it
always has on the wire: callers compare it with naive datetimes. It comes
from the UTC clock whatever the local time zone (``local_time_off_utc``)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.authentication.deps import StaticBearerAuthenticator
from opal_common.authentication.signer import JWTSigner
from opal_common.authentication.types import JWTAlgorithm
from opal_server.security.api import init_security_router

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TTL = timedelta(hours=1)


@pytest.fixture
def client():
    signer = JWTSigner(
        private_key=KEY,
        public_key=KEY.public_key(),
        algorithm=JWTAlgorithm.RS256,
        audience="https://api.opal.example/v1/",
        issuer="https://opal.example/",
    )
    app = FastAPI()
    app.include_router(init_security_router(signer, StaticBearerAuthenticator(None)))
    return TestClient(app)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_the_reported_expiry_is_naive_utc_ttl_from_now(local_time_off_utc, client):
    before = _utc_now_naive()
    response = client.post(
        "/token",
        json={"id": str(uuid4()), "type": "client", "ttl": TTL.total_seconds()},
    )
    after = _utc_now_naive()

    assert response.status_code == 200, response.text
    expired = datetime.fromisoformat(response.json()["details"]["expired"])
    assert expired.tzinfo is None
    assert before + TTL <= expired <= after + TTL
