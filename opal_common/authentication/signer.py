from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from jwt.algorithms import Algorithm, get_default_algorithms
from jwt.api_jwk import PyJWK

from opal_common.authentication.types import JWTAlgorithm, JWTClaims, PrivateKey, PublicKey
from opal_common.logger import logger


class Unauthorized(HTTPException):
    """
    HTTP 401 Unauthorized exception.
    """
    def __init__(self, description="Bearer token is not valid!", **kwargs):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": description,
                **kwargs
            },
            headers={"WWW-Authenticate": "Bearer"}
        )


class InvalidJWTCryptoKeysException(Exception):
    """
    raised when JWT signer provided with invalid crypto keys
    """
    pass

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
        """
        inits the signer if and only if the keys provided to __init__
        were generate together are are valid. otherwise will throw.

        JWT signer can be initialized with empty keys (None),
        in which case signer.enabled == False.

        This allows opal to run both in secure mode (which keys, requires jwt authentication)
        and in insecure mode (good for development and running locally).

        Args:
            private_key (PrivateKey): a valid private key or None
            public_key (PublicKey): a valid public key or None
            algorithm (JWTAlgorithm): the jwt algorithm to use
                (possible values: https://pyjwt.readthedocs.io/en/stable/algorithms.html)
            audience (string): the value for the aud claim: https://tools.ietf.org/html/rfc7519#section-4.1.3
            issuer (string): the value for the iss claim: https://tools.ietf.org/html/rfc7519#section-4.1.1
        """
        self._private_key = private_key
        self._public_key = public_key
        self._algorithm: str = algorithm.value
        self._audience = audience
        self._issuer = issuer
        self._enabled = True
        self._verify_crypto_keys()

    def _verify_crypto_keys(self):
        """
        verifies whether or not valid crypto keys were provided to the signer.
        if both keys are valid, encodes and decodes a JWT to make sure the keys match.

        if both private and public keys are valid and are matching => signer is enabled
        if both private and public keys are None => signer is disabled (self.enabled == False)
        if only one key is valid/not-None => throws ValueError
        any other case => throws ValueError
        """
        if self._private_key is not None and self._public_key is not None:
            # both keys provided, let's make sure these keys were generated correctly
            token = jwt.encode({"some": "payload"}, self._private_key, algorithm=self._algorithm)
            try:
                jwt.decode(token, self._public_key, algorithms=[self._algorithm])
            except jwt.PyJWTError as exc:
                logger.info("JWT Signer key verification failed with error: {err}", err=repr(exc))
                raise InvalidJWTCryptoKeysException("private key and public key do not match!") from exc
            # save jwk
            self._jwk: PyJWK = PyJWK.from_json(self.get_jwk(), algorithm=self._algorithm)
        elif (self._private_key != self._public_key) and (self._private_key is None or self._public_key is None):
            raise ValueError("JWT Signer not valid, only one of private key / public key pair was provided!")
        elif self._private_key is None and self._public_key is None:
            # valid situation, running in dev mode and api security is off
            self._enabled = False
            logger.info("OPAL was not provided with JWT encryption keys, cannot verify api requests!")
        else:
            raise ValueError("Invalid JWT Signer input!")

    def get_jwk(self) -> str:
        """
        returns the jwk json contents
        """
        algorithm: Optional[Algorithm] = get_default_algorithms().get(self._algorithm)
        if algorithm is None:
            raise ValueError(f"invalid jwt algorithm: {self._algorithm}")
        return algorithm.to_jwk(self._public_key)

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

    def sign(self, sub: UUID, token_lifetime: timedelta, custom_claims: dict = {}) -> str:
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
