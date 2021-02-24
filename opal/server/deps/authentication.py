from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security.utils import get_authorization_scheme_param

from opal.server.config import OPAL_WS_TOKEN

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

async def logged_in(authorization: str = Header(...)) -> bool:
    """
    very simple authentication (API Key comparison)
    """
    token = get_token_from_header(authorization)
    return token is not None and token == OPAL_WS_TOKEN

async def verify_logged_in(logged_in: bool = Depends(logged_in)):
    """
    forces api key authentication or throws 401 (can not be used for websocket endpoints)
    """
    if not logged_in:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is not valid!")