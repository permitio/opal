"""The times opal-common writes into tokens and request signatures come from
the UTC clock, whatever the local time zone.

Each test runs with the process's local time five hours east, then west,
of UTC, where a local clock read as UTC is five hours off.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from opal_common.authentication.signer import JWTSigner
from opal_common.authentication.types import JWTAlgorithm
from opal_common.utils import build_aws_rest_auth_headers

AUDIENCE = "https://api.opal.example/v1/"
ISSUER = "https://opal.example/"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(params=["Etc/GMT-5", "Etc/GMT+5"], ids=["utc+5", "utc-5"])
def local_time_off_utc(request):
    before = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    try:
        yield
    finally:
        if before is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = before
        time.tzset()


def test_a_signed_token_is_issued_now_and_expires_after_its_lifetime(
    local_time_off_utc,
):
    signer = JWTSigner(
        private_key=KEY,
        public_key=KEY.public_key(),
        algorithm=JWTAlgorithm.RS256,
        audience=AUDIENCE,
        issuer=ISSUER,
    )
    before = int(time.time())
    token = signer.sign(sub=uuid4(), token_lifetime=timedelta(minutes=5))
    after = int(time.time())

    claims = jwt.decode(
        token, KEY.public_key(), algorithms=["RS256"], audience=AUDIENCE
    )

    assert before <= claims["iat"] <= after
    assert claims["exp"] == claims["iat"] + 300


def test_the_s3_request_signature_is_dated_now(local_time_off_utc):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    headers = build_aws_rest_auth_headers(
        "key-id", "secret", "bucket.example", "/bucket/bundle.tar.gz", "us-east-1"
    )
    after = datetime.now(timezone.utc)

    dated = datetime.strptime(headers["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(
        tzinfo=timezone.utc
    )
    assert before <= dated <= after
    assert f"/{dated:%Y%m%d}/us-east-1/s3/aws4_request" in headers["Authorization"]
