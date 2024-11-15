from fastapi import APIRouter, status
from opal_client.policy.updater import PolicyUpdater
from opal_common.logger import logger
from opal_common.monitoring.prometheus_metrics import (
    opal_client_policy_update_trigger_count,
    opal_client_policy_update_latency,
    opal_client_policy_update_errors
)

def init_policy_router(policy_updater: PolicyUpdater):
    router = APIRouter()

    @router.post("/policy-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_update():
        logger.info("triggered policy update from api")
        opal_client_policy_update_trigger_count.labels(
            source="api",
            status="started",
            update_type="full"
        ).inc()
        try:
            with opal_client_policy_update_latency.labels(source="api", update_type="full").time():
                await policy_updater.trigger_update_policy(force_full_update=True)
                opal_client_policy_update_trigger_count.labels(
                    source="api",
                    status="success",
                    update_type="full"
                ).inc()
                return {"status": "ok"}
        except Exception as e:
            opal_client_policy_update_errors.labels(
                error_type="unknown",
                source="api"
            ).inc()
            logger.error(f"Error during policy update: {str(e)}")
            raise

    return router
