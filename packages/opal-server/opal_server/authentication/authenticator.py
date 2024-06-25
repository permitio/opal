from typing import Optional

from fastapi import Header
from fastapi.exceptions import HTTPException
from opal_common.config import opal_common_config
from opal_common.authentication.authenticator import Authenticator
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.oauth2 import CachedOAuth2Authenticator, OAuth2ClientCredentialsAuthenticator
from opal_common.authentication.signer import JWTSigner
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import JWTVerifier, Unauthorized
from opal_common.logger import logger
from opal_server.config import opal_server_config

class _ServerAuthenticator(Authenticator):
    def __init__(self):
        if opal_common_config.AUTH_TYPE == "oauth2":
            self.__delegate = CachedOAuth2Authenticator(OAuth2ClientCredentialsAuthenticator())
            logger.info("OPAL is running in secure mode - will verify API requests with OAuth2 tokens.")
        else:
            self.__delegate = JWTAuthenticator(self.__signer())

    def __signer(self) -> JWTSigner:
        signer = JWTSigner(
            private_key=opal_server_config.AUTH_PRIVATE_KEY,
            public_key=opal_common_config.AUTH_PUBLIC_KEY,
            algorithm=opal_common_config.AUTH_JWT_ALGORITHM,
            audience=opal_common_config.AUTH_JWT_AUDIENCE,
            issuer=opal_common_config.AUTH_JWT_ISSUER,
        )
        if signer.enabled:
            logger.info("OPAL is running in secure mode - will verify API requests with JWT tokens.")
        else:
            logger.info("OPAL was not provided with JWT encryption keys, cannot verify api requests!")
        return signer

    def _delegate(self) -> dict:
        return self.__delegate

    def signer(self) -> Optional[JWTSigner]:
        if hasattr(self._delegate(), "verifier"):
            return self._delegate().verifier
        else:
            return None

class ServerAuthenticator(_ServerAuthenticator):
    def __call__(self, authorization: Optional[str] = Header(None)) -> JWTClaims:
        return self._delegate()(authorization)

class WebsocketServerAuthenticator(_ServerAuthenticator):
    def __call__(self, authorization: Optional[str] = Header(None)) -> JWTClaims:
        try:
            return self._delegate()(authorization)
        except (Unauthorized, HTTPException):
            return None
