from typing import Optional

from fastapi import Header
from fastapi.exceptions import HTTPException
from opal_common.authentication.authenticator import Authenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import JWTVerifier, Unauthorized


class WebsocketServerAuthenticator(Authenticator):
    def __init__(self, delegate: Authenticator) -> None:
        self._delegate = delegate

    def __call__(self, authorization: Optional[str] = Header(None)) -> JWTClaims:
        try:
            return self._delegate(authorization)
        except (Unauthorized, HTTPException):
            return None
