from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from opal_common.authentication.authz import require_peer_type
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.schemas.security import PeerType

if TYPE_CHECKING:
    from opal_client.client import OpalClient


def init_connectivity_router(client: OpalClient, authenticator: JWTAuthenticator):
    async def require_listener_token(claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(authenticator, claims, PeerType.listener)
        except Unauthorized as e:
            logger.error("Unauthorized connectivity request: {err}", err=repr(e))
            raise

    router = APIRouter(
        prefix="/control-plane",
        dependencies=[Depends(require_listener_token)],
    )

    @router.get("/connectivity", status_code=status.HTTP_200_OK)
    async def get_connectivity_status():
        return {
            "control_plane_connectivity_disabled": client.control_plane_connectivity_disabled,
            "offline_mode_enabled": client.offline_mode_enabled,
        }

    @router.post("/connectivity/disable", status_code=status.HTTP_200_OK)
    async def disable_connectivity():
        if not client.offline_mode_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot disable control plane connectivity: offline mode is not enabled",
            )
        if client.control_plane_connectivity_disabled:
            return {"status": "already_disabled"}

        await client.disable_control_plane_connectivity()
        return {"status": "disabled"}

    @router.post("/connectivity/enable", status_code=status.HTTP_200_OK)
    async def enable_connectivity():
        if not client.offline_mode_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot enable control plane connectivity: offline mode is not enabled",
            )
        if not client.control_plane_connectivity_disabled:
            return {"status": "already_enabled"}

        await client.enable_control_plane_connectivity()
        return {"status": "enabled"}

    return router
