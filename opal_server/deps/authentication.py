from typing import DefaultDict, Optional
from uuid import UUID

from fastapi import Depends, Header
from fastapi.exceptions import HTTPException
from fastapi.security.utils import get_authorization_scheme_param

from opal_common.authentication.signer import JWTSigner, JWTClaims, Unauthorized
from opal_common.logger import logger

def get_token_from_header(authorization_header: str) -> Optional[str]:
    """
    extracts a bearer token from an HTTP Authorization header.

    when provided bearer token via websocket,
    we cannot use the fastapi built-in: oauth2_scheme.
    """
    if not authorization_header:
        return None

    scheme, token = get_authorization_scheme_param(authorization_header)
    if not token or scheme.lower() != "bearer":
        return None

    return token

def verify_logged_in(signer: JWTSigner, token: Optional[str]) -> UUID:
    """
    forces bearer token authentication with valid JWT or throws 401.
    """
    if not signer.enabled:
        logger.debug("signer diabled, cannot verify requests!")
        return
    if token is None:
        raise Unauthorized(token=token, description="access token was not provided")
    claims: JWTClaims = signer.verify(token)
    subject = claims.get("sub", "")

    invalid = Unauthorized(token=token, description="invalid sub claim")
    if not subject:
        raise invalid
    try:
        return UUID(subject)
    except ValueError:
        raise invalid


class JWTVerifier:
    """
    bearer token authentication for http(s) api endpoints.
    throws 401 if a valid jwt is not provided.
    """
    def __init__(self, signer: JWTSigner):
        self.signer = signer

    def __call__(self, authorization: Optional[str] = Header(None)) -> UUID:
        token = get_token_from_header(authorization)
        return verify_logged_in(self.signer, token)


class JWTVerifierWebsocket:
    """
    bearer token authentication for websocket endpoints.

    with fastapi ws endpoint, we cannot throw http exceptions inside dependencies,
    because no matter the http status code, uvicorn will treat it as http 500.
    see: https://github.com/encode/uvicorn/blob/master/uvicorn/protocols/websockets/websockets_impl.py#L168

    Instead we return a boolean to the endpoint, in order for it to gracefully
    close the connection in case authentication was unsuccessful.

    In this case uvicorn's hardcoded behavior suits us:
    - if websocket.accept() was called, http 200 will be sent
    - if websocket.close() was called instead, http 403 will be sent
    no other status code are supported.
    see: https://github.com/encode/uvicorn/blob/master/uvicorn/protocols/websockets/websockets_impl.py#L189-L207

    thus we return a boolean and the endpoint can use it to potentially call websocket.close()
    """
    def __init__(self, signer: JWTSigner):
        self.signer = signer

    def __call__(self, authorization: Optional[str] = Header(None)) -> bool:
        token = get_token_from_header(authorization)
        try:
            verify_logged_in(self.signer, token)
            return True
        except (Unauthorized, HTTPException):
            return False


class StaticBearerTokenVerifier:
    """
    bearer token authentication for http(s) api endpoints.
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
            raise Unauthorized(token=token, description="unauthorized to access this endpoint!")
