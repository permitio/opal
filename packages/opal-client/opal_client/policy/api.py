from fastapi import APIRouter, status
from opal_client.policy.updater import PolicyUpdater
from opal_common.logger import logger
from opal_common.config import opal_common_config

from opentelemetry import trace

if opal_common_config.ENABLE_OPENTELEMETRY_TRACING:
    tracer = trace.get_tracer(__name__)
else:
    tracer = None

def init_policy_router(policy_updater: PolicyUpdater):
    router = APIRouter()

    @router.post("/policy-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_update():
        logger.info("triggered policy update from api")
        if tracer:
            with tracer.start_as_current_span("opal_client_policy_update_apply") as span:
                return await _handle_policy_update(span)
        else:
            return await _handle_policy_update()

    async def _handle_policy_update(span=None):
        try:
            await policy_updater.trigger_update_policy(force_full_update=True)
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error during policy update: {str(e)}")
            if span:
                span.set_status(trace.StatusCode.ERROR)
                span.set_attribute("error", True)
                span.record_exception(e)
            raise

    return router
