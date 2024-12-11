from fastapi import APIRouter, Depends
from opal_client.config import opal_client_config
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreDetails
from opal_common.authentication.authz import require_peer_type
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.config import opal_common_config
from opal_common.logger import logger
from opal_common.monitoring.otel_metrics import get_meter
from opal_common.schemas.security import PeerType
from opentelemetry import metrics

_policy_store_status_metric = None


def get_policy_store_status_metric():
    global _policy_store_status_metric
    if _policy_store_status_metric is None:
        if not opal_common_config.ENABLE_OPENTELEMETRY_METRICS:
            return None
        meter = get_meter()
        _policy_store_status_metric = meter.create_observable_gauge(
            name="opal_client_policy_store_status",
            description="Current status of the policy store authentication type",
            unit="1",
            callbacks=[_update_policy_store_status],
        )
    return _policy_store_status_metric


def _update_policy_store_status(observer: metrics.ObservableGauge):
    auth_type = opal_client_config.POLICY_STORE_AUTH_TYPE or PolicyStoreAuth.NONE
    status_code = {
        PolicyStoreAuth.NONE: 0,
        PolicyStoreAuth.TOKEN: 1,
        PolicyStoreAuth.OAUTH: 2,
    }.get(auth_type, -1)
    observer.observe(status_code, attributes={"auth_type": auth_type})


def init_policy_store_router(authenticator: JWTAuthenticator):
    router = APIRouter()
    get_policy_store_status_metric()

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
