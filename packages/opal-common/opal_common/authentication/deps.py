from typing import Optional
from uuid import UUID

from fastapi import Header
from fastapi.exceptions import HTTPException
from fastapi.security.utils import get_authorization_scheme_param
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import JWTVerifier, Unauthorized
from opal_common.logger import logger


def get_token_from_header(authorization_header: str) -> Optional[str]:
    """extracts a bearer token from an HTTP Authorization header.

    when provided bearer token via websocket, we cannot use the fastapi
    built-in: oauth2_scheme.
    """
    if not authorization_header:
        return None

    scheme, token = get_authorization_scheme_param(authorization_header)
    if not token or scheme.lower() != "bearer":
        return None

    return token


def verify_logged_in(verifier: JWTVerifier, token: Optional[str]) -> JWTClaims:
    """forces bearer token authentication with valid JWT or throws 401."""
    try:
        if not verifier.enabled:
            logger.debug("JWT verification disabled, cannot verify requests!")
            return {}
        if token is None:
            raise Unauthorized(token=token, description="access token was not provided")
        claims: JWTClaims = verifier.verify(token)
        subject = claims.get("sub", "")

        invalid = Unauthorized(token=token, description="invalid sub claim")
        if not subject:
            raise invalid
        try:
            _ = UUID(subject)
        except ValueError:
            raise invalid

        # returns the entire claims dict so we can do more checks on it if needed
        return claims or {}

    except (Unauthorized, HTTPException) as err:
        # err.details is sometimes string and sometimes dict
        details: dict = {}
        if isinstance(err.detail, dict):
            details = err.detail.copy()
        elif isinstance(err.detail, str):
            details = {"msg": err.detail}
        else:
            details = {"msg": repr(err.detail)}

        # pop the token before logging - tokens should not appear in logs
        details.pop("token", None)

        # logs the error and reraises
        logger.error(
            f"Authentication failed with {err.status_code} due to error: {details}"
        )
        raise


class _JWTAuthenticator:
    def __init__(self, verifier: JWTVerifier):
        self._verifier = verifier

    @property
    def verifier(self) -> JWTVerifier:
        return self._verifier

    @property
    def enabled(self) -> JWTVerifier:
        return self._verifier.enabled


class JWTAuthenticator(_JWTAuthenticator):
    """bearer token authentication for http(s) api endpoints.

    throws 401 if a valid jwt is not provided.
    """

    def __call__(self, authorization: Optional[str] = Header(None)) -> JWTClaims:
        token = get_token_from_header(authorization)
        return verify_logged_in(self._verifier, token)


class WebsocketJWTAuthenticator(_JWTAuthenticator):
    """bearer token authentication for websocket endpoints.

    with fastapi ws endpoint, we cannot throw http exceptions inside dependencies,
    because no matter the http status code, uvicorn will treat it as http 500.
    see: https://github.com/encode/uvicorn/blob/master/uvicorn/protocols/websockets/websockets_impl.py#L168

    Instead we return the claims or None to the endpoint, in order for it to gracefully
    close the connection in case authentication was unsuccessful.

    In this case uvicorn's hardcoded behavior suits us:
    - if websocket.accept() was called, http 200 will be sent
    - if websocket.close() was called instead, http 403 will be sent
    no other status code are supported.
    see: https://github.com/encode/uvicorn/blob/master/uvicorn/protocols/websockets/websockets_impl.py#L189-L207

    thus we return a the claims or None and the endpoint can use it to potentially call websocket.close()
    """

    def __call__(self, authorization: Optional[str] = Header(None)) -> bool:
        token = get_token_from_header(authorization)
        try:
            return verify_logged_in(self._verifier, token)
        except (Unauthorized, HTTPException):
            return None


class StaticBearerAuthenticator:
    """bearer token authentication for http(s) api endpoints.

    throws 401 if token does not match a preconfigured value.
    """

    def __init__(self, preconfigured_token: Optional[str]):
        self._preconfigured_token = preconfigured_token

    def __call__(self, authorization: Optional[str] = Header(None)):
        if self._preconfigured_token is None:
            # always allow
            return

        if authorization is None:
            raise Unauthorized(description="Authorization header is required!")

        token = get_token_from_header(authorization)
        if token is None or token != self._preconfigured_token:
            raise Unauthorized(
                token=token, description="unauthorized to access this endpoint!"
            )
