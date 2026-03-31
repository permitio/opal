from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from opal_common.authentication.authz import require_peer_type
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.schemas.security import PeerType
from pydantic import BaseModel

if TYPE_CHECKING:
    from opal_client.client import OpalClient


class ConnectivityStatus(BaseModel):
    opal_server_connectivity_disabled: bool
    offline_mode_enabled: bool


class ConnectivityActionResult(BaseModel):
    status: Literal[
        "disabled",
        "already_disabled",
        "enabled",
        "already_enabled",
    ]


def init_connectivity_router(client: OpalClient, authenticator: JWTAuthenticator):
    async def require_listener_token(claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(authenticator, claims, PeerType.listener)
        except Unauthorized as e:
            logger.error("Unauthorized connectivity request: {err}", err=repr(e))
            raise

    router = APIRouter(
        prefix="/opal-server",
        dependencies=[Depends(require_listener_token)],
    )

    @router.get(
        "/connectivity",
        status_code=status.HTTP_200_OK,
        response_model=ConnectivityStatus,
        summary="Get OPAL server connectivity status",
        description="Returns the current connectivity state to the OPAL server and whether offline mode is enabled.",
    )
    async def get_connectivity_status():
        return ConnectivityStatus(
            opal_server_connectivity_disabled=client.opal_server_connectivity_disabled,
            offline_mode_enabled=client.offline_mode_enabled,
        )

    @router.post(
        "/connectivity/disable",
        status_code=status.HTTP_200_OK,
        response_model=ConnectivityActionResult,
        summary="Disable OPAL server connectivity",
        description="Stops the policy and data updaters, disconnecting from the OPAL server. "
        "Requires offline mode to be enabled. The policy store continues serving from its current state.",
    )
    async def disable_connectivity():
        if not client.offline_mode_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot disable OPAL server connectivity: offline mode is not enabled",
            )
        changed = await client.disable_opal_server_connectivity()
        return ConnectivityActionResult(
            status="disabled" if changed else "already_disabled"
        )

    @router.post(
        "/connectivity/enable",
        status_code=status.HTTP_200_OK,
        response_model=ConnectivityActionResult,
        summary="Enable OPAL server connectivity",
        description="Starts the policy and data updaters, reconnecting to the OPAL server. "
        "Triggers a full rehydration (policy refetch + data refetch), identical to a reconnect. "
        "Requires offline mode to be enabled.",
    )
    async def enable_connectivity():
        if not client.offline_mode_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot enable OPAL server connectivity: offline mode is not enabled",
            )
        changed = await client.enable_opal_server_connectivity()
        return ConnectivityActionResult(
            status="enabled" if changed else "already_enabled"
        )

    return router
