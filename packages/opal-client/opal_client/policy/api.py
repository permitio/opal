from fastapi import APIRouter, status
from opal_client.policy.updater import PolicyUpdater
from opal_common.logger import logger
from opal_common.monitoring.tracing_utils import start_span
from opentelemetry import trace


def init_policy_router(policy_updater: PolicyUpdater):
    router = APIRouter()

    @router.post("/policy-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_update():
        logger.info("triggered policy update from api")
        async with start_span("opal_client_policy_update_trigger") as span:
            return await _handle_policy_update(span)

    async def _handle_policy_update(span=None):
        try:
            async with start_span("opal_client_policy_update_apply", parent=span):
                await policy_updater.trigger_update_policy(force_full_update=True)
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error during policy update: {str(e)}")
            if span is not None:
                span.set_status(trace.StatusCode.ERROR)
                span.set_attribute("error", True)
                span.record_exception(e)
            raise

    return router
