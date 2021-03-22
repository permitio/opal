import os
import json

from uuid import UUID, uuid4
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

import jwt
from jwt.algorithms import get_default_algorithms, Algorithm
from jwt.api_jwk import PyJWK
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat._types import (
    _PRIVATE_KEY_TYPES,
    _PUBLIC_KEY_TYPES,
)
from fastapi import HTTPException, status

from opal.common.logger import logger

# custom types
PrivateKey = _PRIVATE_KEY_TYPES
PublicKey = _PUBLIC_KEY_TYPES
JWTClaims = Dict[str, Any]


class EncryptionKeyFormat(str, Enum):
    """
    represent the supported formats for storing encryption keys.

    - PEM (https://en.wikipedia.org/wiki/Privacy-Enhanced_Mail)
    - SSH (RFC4716) or short format (RFC4253, section-6.6, explained here: https://coolaj86.com/articles/the-ssh-public-key-format/)
    - DER (https://en.wikipedia.org/wiki/X.690#DER_encoding)
    """
    pem = 'pem'
    ssh = 'ssh'
    der = 'der'

# dynamic enum because pyjwt does not define one
# see: https://pyjwt.readthedocs.io/en/stable/algorithms.html for possible values
JWTAlgorithm = Enum('JWTAlgorithm', [(k,k) for k in get_default_algorithms().keys()])


def convert_public_key_to_jwk(public_key: PublicKey, algo: JWTAlgorithm) -> str:
    """
    returns the jwk json contents
    """
    algorithm: Optional[Algorithm] = get_default_algorithms().get(algo.value)
    if algorithm is None:
        raise ValueError(f"invalid jwt algorithm: {algo.value}")
    algorithm.to_jwk(public_key)


def maybe_decode_multiline_key(key: str) -> str:
    """
    if key contents are passed via env var, we allow to encode multiline keys
    with a simple replace of each newline (\n) char with underscore (_).

    this method detects if the provided key contains such encoding, and if so reverses it.
    """
    if "\n" in key:
        return key

    key = key.replace("_", "\n")
    if not key.endswith("\n"):
        key = key + "\n"
    return key


def cast_private_key(value: str, key_format: EncryptionKeyFormat, passphrase: Optional[str] = None) -> PrivateKey:
    """
    Parse a string into a valid cryptographic private key.
    the string can represent a file path in which the key exists, or the actual key contents.
    """
    if passphrase is None:
        password = None
    else:
        password = passphrase.encode('utf-8')

    if os.path.isfile(value):
        raw_key = open(value, "rb").read()
    else:
        raw_key = maybe_decode_multiline_key(value)

    if key_format == EncryptionKeyFormat.pem:
        return serialization.load_pem_private_key(raw_key, password=password, backend=default_backend())

    if key_format == EncryptionKeyFormat.ssh:
        return serialization.load_ssh_private_key(raw_key, password=password, backend=default_backend())

    if key_format == EncryptionKeyFormat.der:
        return serialization.load_der_private_key(raw_key, password=password, backend=default_backend())


def cast_public_key(value: str, key_format: EncryptionKeyFormat) -> PublicKey:
    """
    Parse a string into a valid cryptographic public key.
    the string can represent a file path in which the key exists, or the actual key contents.
    """

    if os.path.isfile(value):
        raw_key = open(value, "rb").read()
    elif key_format == EncryptionKeyFormat.ssh: # ssh key format is one line
        raw_key = value
    else:
        raw_key = maybe_decode_multiline_key(value)

    if key_format == EncryptionKeyFormat.pem:
        return serialization.load_pem_public_key(raw_key, backend=default_backend())

    if key_format == EncryptionKeyFormat.ssh:
        return serialization.load_ssh_public_key(raw_key, backend=default_backend())

    if key_format == EncryptionKeyFormat.der:
        return serialization.load_der_public_key(raw_key, backend=default_backend())


class Unauthorized(HTTPException):
    """
    HTTP 401 Unauthorized exception.
    """
    def __init__(self, *, description="Bearer token is not valid!", **kwargs):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": description,
                **kwargs
            },
            headers={"WWW-Authenticate": "Bearer"}
        )


class JWTSigner:
    """
    given cryptographic keys, signs and verifies jwt tokens.
    """
    def __init__(
        self,
        private_key: Optional[PrivateKey],
        public_key: Optional[PublicKey],
        algorithm: JWTAlgorithm,
        audience: str,
        issuer: str,
    ):
        self._private_key = private_key
        self._public_key = public_key
        self._algorithm: str = algorithm.value
        self._audience = audience
        self._issuer = issuer
        self._enabled = True
        self._verify_crypto_keys()

    def _verify_crypto_keys(self):
        if self._private_key is not None and self._public_key is not None:
            # both keys provided, let's make sure these keys were generated correctly
            token = jwt.encode({"some": "payload"}, self._private_key, algorithm=self._algorithm)
            try:
                jwt.decode(token, self._public_key, algorithms=[self._algorithm])
            except jwt.PyJWTError as e:
                logger.info("JWT Signer key verification failed with error: {err}", err=e)
                raise
            # save jwk
            self._jwk: PyJWK = PyJWK.from_json(
                convert_public_key_to_jwk(
                    self._public_key,
                    getattr(JWTAlgorithm, self._algorithm)
                )
            )
        elif (self._private_key != self._public_key) and (self._private_key is None or self._public_key is None):
            raise ValueError("JWT Signer not valid, only one of private key / public key pair was provided!")
        elif self._private_key is None and self._public_key is None:
            # valid situation, running in dev mode and api security is off
            self._enabled = False
            logger.info("OPAL was not provided with JWT encryption keys, cannot verify api requests!")
        else:
            raise ValueError("Invalid JWT Signer input!")

    @property
    def enabled(self):
        """
        whether or not the signer has valid cryptographic keys
        """
        return self._enabled

    def verify(self, token: str) -> JWTClaims:
        """
        verifies a JWT token is valid.
        if valid returns dict with jwt claims, otherwise throws.
        """
        try:
            return jwt.decode(
                token,
                self._public_key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer
            )
        except jwt.ExpiredSignatureError:
            raise Unauthorized(token=token, description="Access token is expired")
        except jwt.InvalidAudienceError:
            raise Unauthorized(token=token, description="Invalid access token: invalid audience claim")
        except jwt.InvalidIssuerError:
            raise Unauthorized(token=token, description="Invalid access token: invalid issuer claim")
        except jwt.DecodeError:
            raise Unauthorized(token=token, description="Could not decode access token")
        except Exception:
            raise Unauthorized(token=token, description="Unknown JWT error")

    def sign(self, sub: UUID, token_lifetime: timedelta, custom_claims: dict = {}):
        payload = {}
        issued_at = datetime.utcnow()
        expire_at = issued_at + token_lifetime
        payload = {
            "iat": issued_at,
            "exp": expire_at,
            "aud": self._audience,
            "iss": self._issuer,
            "sub": sub.hex,
        }
        if custom_claims:
            payload.update(custom_claims)

        headers = {}
        if self._jwk.key_id is not None:
            headers = {"kid": self._jwk.key_id}
        return jwt.encode(payload, self._private_key, algorithm=self._algorithm, headers=headers)