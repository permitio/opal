from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import jwt
from jwt.api_jwk import PyJWK
from opal_common.authentication.types import (
    JWTAlgorithm,
    JWTClaims,
    PrivateKey,
    PublicKey,
)
from opal_common.authentication.verifier import JWTVerifier
from opal_common.logger import logger


class InvalidJWTCryptoKeysException(Exception):
    """raised when JWT signer provided with invalid crypto keys."""

    pass


class JWTSigner(JWTVerifier):
    """given cryptographic keys, signs and verifies jwt tokens."""

    def __init__(
        self,
        private_key: Optional[PrivateKey],
        public_key: Optional[PublicKey],
        algorithm: JWTAlgorithm,
        audience: str,
        issuer: str,
    ):
        """inits the signer if and only if the keys provided to __init__ were
        generate together are are valid. otherwise will throw.

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
        super().__init__(
            public_key=public_key, algorithm=algorithm, audience=audience, issuer=issuer
        )
        self._private_key = private_key
        self._verify_crypto_keys()

    def _verify_crypto_keys(self):
        """verifies whether or not valid crypto keys were provided to the
        signer. if both keys are valid, encodes and decodes a JWT to make sure
        the keys match.

        if both private and public keys are valid and are matching =>
        signer is enabled if both private and public keys are None =>
        signer is disabled (self.enabled == False) if only one key is
        valid/not-None => throws ValueError any other case => throws
        ValueError
        """
        if self._private_key is not None and self._public_key is not None:
            # both keys provided, let's make sure these keys were generated correctly
            token = jwt.encode(
                {"some": "payload"}, self._private_key, algorithm=self._algorithm
            )
            try:
                jwt.decode(token, self._public_key, algorithms=[self._algorithm])
            except jwt.PyJWTError as exc:
                logger.info(
                    "JWT Signer key verification failed with error: {err}",
                    err=repr(exc),
                )
                raise InvalidJWTCryptoKeysException(
                    "private key and public key do not match!"
                ) from exc
            # save jwk
            self._jwk: PyJWK = PyJWK.from_json(
                self.get_jwk(), algorithm=self._algorithm
            )
        elif self._private_key is None and self._public_key is not None:
            raise ValueError(
                "JWT Signer not valid, you provided a public key without a private key!"
            )
        elif self._private_key is not None and self._public_key is None:
            raise ValueError(
                "JWT Signer not valid, you provided a private key without a public key!"
            )
        elif self._private_key is None and self._public_key is None:
            # valid situation, running in dev mode and api security is off
            self._disable()
        else:
            raise ValueError("Invalid JWT Signer input!")

    def sign(
        self, sub: UUID, token_lifetime: timedelta, custom_claims: dict = {}
    ) -> str:
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
        return jwt.encode(
            payload, self._private_key, algorithm=self._algorithm, headers=headers
        )
