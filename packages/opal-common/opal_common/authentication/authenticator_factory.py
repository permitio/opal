from opal_common.authentication.authenticator import Authenticator
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.verifier import JWTVerifier, Unauthorized
from opal_common.config import opal_common_config
from opal_common.logger import logger

from .oauth2 import CachedOAuth2Authenticator, OAuth2ClientCredentialsAuthenticator


class AuthenticatorFactory:
    @staticmethod
    def create() -> Authenticator:
        if opal_common_config.AUTH_TYPE == "oauth2":
            logger.info(
                "OPAL is running in secure mode - will authenticate API requests with OAuth2 tokens."
            )
            return CachedOAuth2Authenticator(OAuth2ClientCredentialsAuthenticator())
        else:
            return JWTAuthenticator(AuthenticatorFactory.__verifier())

    @staticmethod
    def __verifier() -> JWTVerifier:
        verifier = JWTVerifier(
            public_key=opal_common_config.AUTH_PUBLIC_KEY,
            algorithm=opal_common_config.AUTH_JWT_ALGORITHM,
            audience=opal_common_config.AUTH_JWT_AUDIENCE,
            issuer=opal_common_config.AUTH_JWT_ISSUER,
        )
        if not verifier.enabled:
            logger.info(
                "API authentication disabled (public encryption key was not provided)"
            )

        return verifier
