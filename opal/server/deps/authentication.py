from typing import DefaultDict, Optional
from uuid import UUID

from fastapi import Depends, Header
from fastapi.exceptions import HTTPException
from fastapi.security.utils import get_authorization_scheme_param

from opal.common.authentication.jwt import JWTSigner, JWTClaims, Unauthorized
from opal.common.logger import logger

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


async def verify_logged_in(signer: JWTSigner, authorization: str = Header(...)) -> UUID:
    """
    forces bearer token authentication with valid JWT or throws 401 (can not be used for websocket endpoints)
    """
    if not signer.enabled:
        logger.debug("signer diabled, cannot verify request!")
        return
    token = get_token_from_header(authorization)
    claims: JWTClaims = signer.verify(token)
    subject = claims.get("sub", "")

    invalid = Unauthorized(token=token, description="invalid sub claim")
    if not subject:
        raise invalid
    try:
        return UUID(subject)
    except ValueError:
        raise invalid


async def logged_in(signer: JWTSigner, authorization: str = Header(...)) -> bool:
    """
    less violent bearer token authentication (instead of throwing 401, returns True or False)
    """
    try:
        verify_logged_in(signer=signer, authorization=authorization)
        return True
    except (Unauthorized, HTTPException):
        return False

