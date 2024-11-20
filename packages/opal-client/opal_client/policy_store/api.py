from fastapi import APIRouter, Depends
from opal_client.config import opal_client_config
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreDetails
from opal_common.authentication.authz import require_peer_type
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.schemas.security import PeerType
from opal_common.config import opal_common_config

from opentelemetry import metrics

if opal_common_config.ENABLE_OPENTELEMETRY_METRICS:
    meter = metrics.get_meter(__name__)

    def policy_store_status_callback(observable_gauge):
        auth_type = opal_client_config.POLICY_STORE_AUTH_TYPE or PolicyStoreAuth.NONE
        observable_gauge.observe(
            1,
            attributes={"auth_type": str(auth_type)},
        )

    policy_store_status_metric = meter.create_observable_gauge(
        name="opal_client_policy_store_status",
        description="Current status of the policy store authentication type",
        unit="1",
        callbacks=[policy_store_status_callback],
    )
else:
    meter = None
    policy_store_status_metric = None

def init_policy_store_router(authenticator: JWTAuthenticator):
    router = APIRouter()

    @router.get(
        "/policy-store/config",
        response_model=PolicyStoreDetails,
        response_model_exclude_none=True,
        # Deprecating this route
        deprecated=True,
    )
    async def get_policy_store_details(claims: JWTClaims = Depends(authenticator)):
            try:
                require_peer_type(
                    authenticator, claims, PeerType.listener
                )  # may throw Unauthorized
            except Unauthorized as e:
                logger.error(f"Unauthorized to publish update: {repr(e)}")
                raise

            token = None
            oauth_client_secret = None
            if not opal_client_config.EXCLUDE_POLICY_STORE_SECRETS:
                token = opal_client_config.POLICY_STORE_AUTH_TOKEN
                oauth_client_secret = (
                    opal_client_config.POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET
                )

            auth_type = opal_client_config.POLICY_STORE_AUTH_TYPE or PolicyStoreAuth.NONE

            return PolicyStoreDetails(
                url=opal_client_config.POLICY_STORE_URL,
                token=token or None,
                auth_type=auth_type,
                oauth_client_id=opal_client_config.POLICY_STORE_AUTH_OAUTH_CLIENT_ID
                or None,
                oauth_client_secret=oauth_client_secret or None,
                oauth_server=opal_client_config.POLICY_STORE_AUTH_OAUTH_SERVER or None,
            )

    return router
