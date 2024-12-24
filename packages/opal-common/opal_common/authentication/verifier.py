from typing import Optional

import jwt
from fastapi import HTTPException, status
from jwt.algorithms import Algorithm, get_default_algorithms
from jwt.api_jwk import PyJWK
from opal_common.authentication.types import JWTAlgorithm, JWTClaims, PublicKey
from opal_common.logger import logger


class Unauthorized(HTTPException):
    """HTTP 401 Unauthorized exception."""

    def __init__(self, description="Bearer token is not valid!", **kwargs):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": description, **kwargs},
            headers={"WWW-Authenticate": "Bearer"},
        )


class JWTVerifier:
    """given a cryptographic public key, can verify jwt tokens."""

    def __init__(
        self,
        public_key: Optional[PublicKey],
        algorithm: JWTAlgorithm,
        audience: str,
        issuer: str,
    ):
        """inits the signer if and only if the keys provided to __init__ were
        generate together are are valid. otherwise will throw.

        JWT verifier can be initialized without a public key (None)
        in which case verifier.enabled == False and jwt verification is turned off.

        This allows opal to run both in secure mode (with jwt-based authentication)
        and in insecure mode (intended for development environments and running locally).

        Args:
            public_key (PublicKey): a valid public key or None
            algorithm (JWTAlgorithm): the jwt algorithm to use
                (possible values: https://pyjwt.readthedocs.io/en/stable/algorithms.html)
            audience (string): the value for the aud claim: https://tools.ietf.org/html/rfc7519#section-4.1.3
            issuer (string): the value for the iss claim: https://tools.ietf.org/html/rfc7519#section-4.1.1
        """
        self._public_key = public_key
        self._algorithm: str = algorithm.value
        self._audience = audience
        self._issuer = issuer
        self._enabled = True
        self._verify_public_key()

    def _verify_public_key(self):
        """verifies whether or not the public key is a valid crypto key
        (according to the JWT algorithm)."""
        if self._public_key is not None:
            # save jwk
            try:
                self._jwk: PyJWK = PyJWK.from_json(
                    self.get_jwk(), algorithm=self._algorithm
                )
            except jwt.exceptions.InvalidKeyError as e:
                logger.error(f"Invalid public key for jwt verification, error: {e}!")
                self._disable()
        else:
            self._disable()

    def get_jwk(self) -> str:
        """returns the jwk json contents."""
        algorithm: Optional[Algorithm] = get_default_algorithms().get(self._algorithm)
        if algorithm is None:
            raise ValueError(f"invalid jwt algorithm: {self._algorithm}")
        return algorithm.to_jwk(self._public_key)

    def _disable(self):
        self._enabled = False

    @property
    def enabled(self):
        """whether or not the verifier has valid cryptographic keys."""
        return self._enabled

    def verify(self, token: str) -> JWTClaims:
        """verifies a JWT token is valid.

        if valid returns dict with jwt claims, otherwise throws.
        """
        try:
            return jwt.decode(
                token,
                self._public_key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.ExpiredSignatureError:
            raise Unauthorized(token=token, description="Access token is expired")
        except jwt.InvalidAudienceError:
            raise Unauthorized(
                token=token, description="Invalid access token: invalid audience claim"
            )
        except jwt.InvalidIssuerError:
            raise Unauthorized(
                token=token, description="Invalid access token: invalid issuer claim"
            )
        except jwt.DecodeError:
            raise Unauthorized(token=token, description="Could not decode access token")
        except Exception:
            raise Unauthorized(token=token, description="Unknown JWT error")
