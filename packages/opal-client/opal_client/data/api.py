from typing import Optional

from fastapi import APIRouter, HTTPException, status
from opal_client.data.updater import DataUpdater
from opal_common.logger import logger
from opal_common.config import opal_common_config
from opentelemetry import trace

if opal_common_config.ENABLE_OPENTELEMETRY_TRACING:
    tracer = trace.get_tracer(__name__)
else:
    tracer = None

def init_data_router(data_updater: Optional[DataUpdater]):
    router = APIRouter()

    @router.post("/data-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_data_update():
        logger.info("triggered policy data update from api")
        if tracer:
            with tracer.start_as_current_span("opal_client_data_update_trigger") as span:
                return await _handle_policy_data_update(span)
        else:
            return await _handle_policy_data_update()

    async def _handle_policy_data_update(span=None):
        try:
            if data_updater:
                if tracer and span:
                    with tracer.start_as_current_span("opal_client_data_update_apply"):
                        await data_updater.get_base_policy_data(
                            data_fetch_reason="request from sdk"
                        )
                else:
                    await data_updater.get_base_policy_data(
                        data_fetch_reason="request from sdk"
                    )
                return {"status": "ok"}
            else:
                if span:
                    span.set_status(trace.StatusCode.ERROR)
                    span.set_attribute("error", True)
                    span.set_attribute("error_type", "updater_disabled")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Data Updater is currently disabled. Dynamic data updates are not available.",
                )
        except Exception as e:
            logger.error(f"Error during data update: {str(e)}")
            if span:
                span.set_status(trace.StatusCode.ERROR)
                span.set_attribute("error", True)
                span.record_exception(e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update data"
            )
    return router
