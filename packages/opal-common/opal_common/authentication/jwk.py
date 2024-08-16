import jwt
import httpx

from cachetools import TTLCache
from opal_common.authentication.verifier import Unauthorized

class JWKManager:
    def __init__(self, openid_configuration_url, jwt_algorithm, cache_maxsize, cache_ttl):
        self._openid_configuration_url = openid_configuration_url
        self._jwt_algorithm = jwt_algorithm
        self._cache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl)

    def public_key(self, token):
        header = jwt.get_unverified_header(token)
        kid = header['kid']

        public_key = self._cache.get(kid)
        if public_key is None:
            public_key = self._fetch_public_key(token)
            self._cache[kid] = public_key

        return public_key

    def _fetch_public_key(self, token: str):
        try:
            return self._jwks_client().get_signing_key_from_jwt(token).key
        except Exception:
            raise Unauthorized(description="unknown JWT error")

    def _jwks_client(self):
        oidc_config = self._openid_configuration()
        signing_algorithms = oidc_config["id_token_signing_alg_values_supported"]
        if self._jwt_algorithm.name not in signing_algorithms:
            raise Unauthorized(description="unknown JWT algorithm")
        if "jwks_uri" not in oidc_config:
            raise Unauthorized(description="missing 'jwks_uri' property")
        return jwt.PyJWKClient(oidc_config["jwks_uri"])

    def _openid_configuration(self):
        response = httpx.get(self._openid_configuration_url)

        if response.status_code != httpx.codes.OK:
            raise Unauthorized(description=f"invalid status code {response.status_code}")

        return response.json()
