from opal_common.authentication.authenticator import Authenticator
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.oauth2 import (
    CachedOAuth2Authenticator,
    OAuth2ClientCredentialsAuthenticator,
)
from opal_common.authentication.signer import JWTSigner
from opal_common.config import opal_common_config
from opal_common.logger import logger
from opal_server.config import opal_server_config

from .authenticator import WebsocketServerAuthenticator


class ServerAuthenticatorFactory:
    @staticmethod
    def create() -> Authenticator:
        if opal_common_config.AUTH_TYPE == "oauth2":
            logger.info(
                "OPAL is running in secure mode - will verify API requests with OAuth2 tokens."
            )
            return CachedOAuth2Authenticator(OAuth2ClientCredentialsAuthenticator())
        else:
            return JWTAuthenticator(ServerAuthenticatorFactory.__signer())

    @staticmethod
    def __signer() -> JWTSigner:
        signer = JWTSigner(
            private_key=opal_server_config.AUTH_PRIVATE_KEY,
            public_key=opal_common_config.AUTH_PUBLIC_KEY,
            algorithm=opal_common_config.AUTH_JWT_ALGORITHM,
            audience=opal_common_config.AUTH_JWT_AUDIENCE,
            issuer=opal_common_config.AUTH_JWT_ISSUER,
        )
        if signer.enabled:
            logger.info(
                "OPAL is running in secure mode - will verify API requests with JWT tokens."
            )
        else:
            logger.info(
                "OPAL was not provided with JWT encryption keys, cannot verify api requests!"
            )
        return signer


class WebsocketServerAuthenticatorFactory:
    @staticmethod
    def create() -> Authenticator:
        return WebsocketServerAuthenticator(ServerAuthenticatorFactory.create())
