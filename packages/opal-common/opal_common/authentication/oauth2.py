import asyncio
import httpx
import time

from cachetools import cached, TTLCache
from fastapi import Header
from httpx import AsyncClient, BasicAuth
from opal_common.authentication.authenticator import Authenticator
from opal_common.authentication.deps import get_token_from_header
from opal_common.authentication.jwk import JWKManager
from opal_common.authentication.signer import JWTSigner
from opal_common.authentication.verifier import JWTVerifier, Unauthorized
from opal_common.config import opal_common_config
from typing import Optional

class _OAuth2Authenticator(Authenticator):
    async def authenticate(self, headers):
        if "Authorization" not in headers:
            token = await self.token()
            headers['Authorization'] = f"Bearer {token}"


class OAuth2ClientCredentialsAuthenticator(_OAuth2Authenticator):
    def __init__(self) -> None:
        self._client_id = opal_common_config.OAUTH2_CLIENT_ID
        self._client_secret = opal_common_config.OAUTH2_CLIENT_SECRET
        self._token_url = opal_common_config.OAUTH2_TOKEN_URL
        self._introspect_url = opal_common_config.OAUTH2_INTROSPECT_URL
        self._jwt_algorithm = opal_common_config.OAUTH2_JWT_ALGORITHM
        self._jwt_audience = opal_common_config.OAUTH2_JWT_AUDIENCE
        self._jwt_issuer = opal_common_config.OAUTH2_JWT_ISSUER
        self._jwk_manager = JWKManager(
            opal_common_config.OAUTH2_OPENID_CONFIGURATION_URL,
            opal_common_config.OAUTH2_JWT_ALGORITHM,
            opal_common_config.OAUTH2_JWK_CACHE_MAXSIZE,
            opal_common_config.OAUTH2_JWK_CACHE_TTL,
        )

        cfg = opal_common_config.OAUTH2_EXACT_MATCH_CLAIMS
        if cfg is None:
            self._exact_match_claims = {}
        else:
            self._exact_match_claims = dict(map(lambda x: x.split("="), cfg.split(",")))

        cfg = opal_common_config.OAUTH2_REQUIRED_CLAIMS
        if cfg is None:
            self._required_claims = []
        else:
            self._required_claims = cfg.split(",")

    @property
    def enabled(self):
        return True

    def signer(self) -> Optional[JWTSigner]:
        return None

    async def token(self):
        auth = BasicAuth(self._client_id, self._client_secret)
        data = {"grant_type": "client_credentials"}

        async with AsyncClient() as client:
            response = await client.post(self._token_url, auth=auth, data=data)
            return (response.json())['access_token']

    def __call__(self, authorization: Optional[str] = Header(None)) -> {}:
        token = get_token_from_header(authorization)
        return self.verify(token)

    def verify(self, token: str) -> {}:
        if self._introspect_url is not None:
            claims = self._verify_opaque(token)
        else:
            claims = self._verify_jwt(token)

        self._verify_exact_match_claims(claims)
        self._verify_required_claims(claims)

        return claims

    def _verify_opaque(self, token: str) -> {}:
        response = httpx.post(self._introspect_url, data={'token': token})

        if response.status_code != httpx.codes.OK:
            raise Unauthorized(description=f"invalid status code {response.status_code}")

        claims = response.json()
        active = claims.get("active", False)
        if not active:
            raise Unauthorized(description="inactive token")

        return claims or {}

    def _verify_jwt(self, token: str) -> {}:
        public_key = self._jwk_manager.public_key(token)

        verifier = JWTVerifier(
            public_key=public_key,
            algorithm=self._jwt_algorithm,
            audience=self._jwt_audience,
            issuer=self._jwt_issuer,
        )
        claims = verifier.verify(token)

        return claims or {}

    def _verify_exact_match_claims(self, claims):
        for key, value in self._exact_match_claims.items():
            if key not in claims:
                raise Unauthorized(description=f"missing required '{key}' claim")
            elif claims[key] != value:
                raise Unauthorized(description=f"invalid '{key}' claim value")

    def _verify_required_claims(self, claims):
        for claim in self._required_claims:
            if claim not in claims:
                raise Unauthorized(description=f"missing required '{claim}' claim")


class CachedOAuth2Authenticator(_OAuth2Authenticator):
    lock = asyncio.Lock()

    def __init__(self, delegate: OAuth2ClientCredentialsAuthenticator) -> None:
        self._token = None
        self._exp = None
        self._exp_margin = opal_common_config.OAUTH2_EXP_MARGIN
        self._delegate = delegate

    @property
    def enabled(self):
        return self._delegate.enabled

    def signer(self) -> Optional[JWTSigner]:
        return self._delegate.signer()

    def _expired(self):
        if self._token is None:
            return True

        now = int(time.time())
        return now > self._exp - self._exp_margin

    async def token(self):
        if not self._expired():
            return self._token

        async with CachedOAuth2Authenticator.lock:
            if not self._expired():
                return self._token

            token = await self._delegate.token()
            claims = self._delegate.verify(token)

            self._token = token
            self._exp = claims['exp']

            return self._token

    @cached(cache=TTLCache(
        maxsize=opal_common_config.OAUTH2_TOKEN_VERIFY_CACHE_MAXSIZE,
        ttl=opal_common_config.OAUTH2_TOKEN_VERIFY_CACHE_TTL
    ))
    def __call__(self, authorization: Optional[str] = Header(None)) -> {}:
        return self._delegate(authorization)
