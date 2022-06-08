from fastapi import APIRouter, Depends
from opal_client.config import opal_client_config
from opal_client.policy_store.schemas import PolicyStoreDetails
from opal_common.authentication.authz import require_peer_type
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.schemas.security import PeerType


def init_policy_store_router(authenticator: JWTAuthenticator):
    router = APIRouter()

    @router.get(
        "/policy-store/config",
        response_model=PolicyStoreDetails,
        response_model_exclude_none=True,
    )
    async def get_policy_store_details(claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(
                authenticator, claims, PeerType.listener
            )  # may throw Unauthorized
        except Unauthorized as e:
            logger.error(f"Unauthorized to publish update: {repr(e)}")
            raise

        return PolicyStoreDetails(
            url=opal_client_config.POLICY_STORE_URL,
            token=opal_client_config.POLICY_STORE_AUTH_TOKEN or None,
        )

    return router
