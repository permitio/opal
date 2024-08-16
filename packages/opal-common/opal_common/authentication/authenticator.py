from abc import abstractmethod
from typing import Optional

from fastapi import Header
from opal_common.config import opal_common_config
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import JWTVerifier, Unauthorized
from opal_common.logger import logger
from .oauth2 import CachedOAuth2Authenticator, OAuth2ClientCredentialsAuthenticator

class Authenticator:
    @property
    def enabled(self):
        return self._delegate().enabled

    async def authenticate(self, headers):
        if hasattr(self._delegate(), "authenticate") and callable(getattr(self._delegate(), "authenticate")):
            await self._delegate().authenticate(headers)

    @abstractmethod
    def _delegate(self) -> dict:
        pass

class _ClientAuthenticator(Authenticator):
    def __init__(self):
        if opal_common_config.AUTH_TYPE == "oauth2":
            self.__delegate = CachedOAuth2Authenticator(OAuth2ClientCredentialsAuthenticator())
            logger.info("OPAL is running in secure mode - will authenticate API requests.")
        else:
            self.__delegate = JWTAuthenticator(self.__verifier())

    def __verifier(self) -> JWTVerifier:
        verifier = JWTVerifier(
            public_key=opal_common_config.AUTH_PUBLIC_KEY,
            algorithm=opal_common_config.AUTH_JWT_ALGORITHM,
            audience=opal_common_config.AUTH_JWT_AUDIENCE,
            issuer=opal_common_config.AUTH_JWT_ISSUER,
        )
        if not verifier.enabled:
            logger.info("API authentication disabled (public encryption key was not provided)")

        return verifier

    def _delegate(self) -> dict:
        return self.__delegate

class ClientAuthenticator(_ClientAuthenticator):
    def __call__(self, authorization: Optional[str] = Header(None)) -> JWTClaims:
        return self._delegate()(authorization)
