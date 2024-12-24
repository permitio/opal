from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from opal_client.callbacks.register import CallbacksRegister
from opal_client.config import opal_client_config
from opal_common.authentication.authz import require_peer_type
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.schemas.data import CallbackEntry
from opal_common.schemas.security import PeerType
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR


def init_callbacks_api(authenticator: JWTAuthenticator, register: CallbacksRegister):
    async def require_listener_token(claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(
                authenticator, claims, PeerType.listener
            )  # may throw Unauthorized
        except Unauthorized as e:
            logger.error(f"Unauthorized to publish update: {repr(e)}")
            raise

    # all the methods in this router requires a valid JWT token with peer_type == listener
    router = APIRouter(
        prefix="/callbacks", dependencies=[Depends(require_listener_token)]
    )

    @router.get("", response_model=List[CallbackEntry])
    async def list_callbacks():
        """list all the callbacks currently registered by OPAL client."""
        return list(register.all())

    @router.get("/{key}", response_model=CallbackEntry)
    async def get_callback_by_key(key: str):
        """get a callback by its key (if such callback is indeed
        registered)."""
        callback = register.get(key)
        if callback is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no callback found with this key",
            )
        return callback

    @router.post("", response_model=CallbackEntry)
    async def register_callback(entry: CallbackEntry):
        """register a new callback by OPAL client, to be called on OPA state
        updates."""
        saved_key = register.put(url=entry.url, config=entry.config, key=entry.key)
        saved_entry = register.get(saved_key)
        if saved_entry is None:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not register callback",
            )
        return saved_entry

    @router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
    async def get_callback_by_key(key: str):
        """unregisters a callback identified by its key (if such callback is
        indeed registered)."""
        callback = register.get(key)
        if callback is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no callback found with this key",
            )
        register.remove(key)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
