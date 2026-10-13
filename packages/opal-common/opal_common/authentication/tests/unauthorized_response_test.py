"""A rejected bearer token is never echoed back in the 401 body (which clients
log) nor written to the server's logs."""

import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from opal_common.authentication.deps import JWTAuthenticator, StaticBearerAuthenticator
from opal_common.authentication.types import JWTAlgorithm
from opal_common.authentication.verifier import JWTVerifier
from opal_common.tests.redaction_fixtures import capture_logs

AUDIENCE = "https://api.opal.example/v1/"
ISSUER = "https://opal.example/"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _signed(**claims) -> str:
    now = int(time.time())
    payload = {
        "sub": uuid4().hex,
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": now,
        "exp": now + 60,
        **claims,
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")


def _client() -> TestClient:
    app = FastAPI()
    verifier = JWTVerifier(
        PRIVATE_KEY.public_key(), JWTAlgorithm.RS256, AUDIENCE, ISSUER
    )
    assert verifier.enabled
    jwt_auth = JWTAuthenticator(verifier)
    static_auth = StaticBearerAuthenticator("expected-master-token")

    @app.get("/jwt", dependencies=[Depends(jwt_auth)])
    async def jwt_protected():  # pragma: no cover - never reached on 401
        return {}

    @app.get("/static", dependencies=[Depends(static_auth)])
    async def static_protected():  # pragma: no cover - never reached on 401
        return {}

    return TestClient(app)


@pytest.mark.parametrize(
    "path,token,error",
    [
        ("/jwt", "FAKE-KEY-123", "Could not decode access token"),
        ("/jwt", _signed(exp=int(time.time()) - 60), "Access token is expired"),
        ("/jwt", _signed(aud="https://other.example/"), "invalid audience claim"),
        ("/jwt", _signed(iss="https://other.example/"), "invalid issuer claim"),
        ("/jwt", _signed(nbf=int(time.time()) + 3600), "Unknown JWT error"),
        ("/static", "FAKE-KEY-123", "unauthorized to access this endpoint!"),
    ],
    ids=["undecodable", "expired", "audience", "issuer", "not-yet-valid", "static"],
)
def test_rejected_token_is_not_echoed(path, token, error):
    with capture_logs() as logs:
        response = _client().get(path, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert error in response.json()["detail"]["error"]
    assert token not in response.text
    assert token not in logs.combined
