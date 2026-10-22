"""How JWTVerifier treats the base64url encoding of a token's signature.

Both behaviours come from PyJWT, not OPAL, and are why requires.txt floors
pyjwt at 2.15.1:

- PyJWT 2.14.0 rejects a non-canonical signature segment (one whose unused
  trailing bits are set), closing GHSA-hxm8-2xgr-2p9m: such a token decodes
  to the same signature as the canonical one, so a revocation list keyed on
  the raw token missed it. 2.13.0 accepted it.
- PyJWT 2.15.1 accepts a segment carrying trailing ``=`` padding again, as
  issued by AWS ALB and similar systems. 2.14.0 and 2.15.0 rejected it.
"""

import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from opal_common.authentication.types import JWTAlgorithm
from opal_common.authentication.verifier import JWTVerifier, Unauthorized

AUDIENCE = "https://api.opal.example/v1/"
ISSUER = "https://opal.example/"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
B64URL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _verifier() -> JWTVerifier:
    verifier = JWTVerifier(
        PRIVATE_KEY.public_key(), JWTAlgorithm.RS256, AUDIENCE, ISSUER
    )
    assert verifier.enabled
    return verifier


def _signed() -> str:
    now = int(time.time())
    payload = {"sub": uuid4().hex, "aud": AUDIENCE, "iss": ISSUER, "exp": now + 60}
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")


def _with_signature(token: str, signature: str) -> str:
    header, payload, _ = token.split(".")
    return f"{header}.{payload}.{signature}"


def test_canonical_token_verifies():
    token = _signed()
    assert _verifier().verify(token)["iss"] == ISSUER


def test_padded_signature_verifies():
    token = _signed()
    signature = token.split(".")[2]
    # A 2048-bit RSA signature is 256 bytes: 342 base64url characters, which
    # standard base64 pads to 344.
    assert len(signature) % 4 == 2
    padded = _with_signature(token, signature + "==")
    assert _verifier().verify(padded)["iss"] == ISSUER


def test_non_canonical_signature_is_rejected():
    token = _signed()
    signature = token.split(".")[2]
    # 342 characters carry 2052 bits for a 2048-bit signature, so the low 4
    # bits of the last character are unused. Setting one changes the encoding
    # but not the decoded bytes.
    last = B64URL.index(signature[-1])
    assert last & 0b1111 == 0
    tampered = _with_signature(token, signature[:-1] + B64URL[last | 1])
    assert tampered != token
    with pytest.raises(Unauthorized):
        _verifier().verify(tampered)
