from typing import Optional

from fastapi import APIRouter, HTTPException, status
from opal_client.data.updater import DataUpdater
from opal_common.logger import logger
from opal_common.monitoring.tracing_utils import start_span
from opentelemetry import trace


def init_data_router(data_updater: Optional[DataUpdater]):
    router = APIRouter()

    @router.post("/data-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_data_update():
        logger.info("triggered policy data update from api")
        async with start_span("opal_client_data_update_trigger") as span:
            return await _handle_policy_data_update(span)

    async def _handle_policy_data_update(span=None):
        try:
            if data_updater:
                async with start_span("opal_client_data_update_apply") if span else (
                    await None
                ):
                    await data_updater.get_base_policy_data(
                        data_fetch_reason="request from sdk"
                    )
                return {"status": "ok"}
            else:
                if span is not None:
                    span.set_status(trace.StatusCode.ERROR)
                    span.set_attribute("error", True)
                    span.set_attribute("error_type", "updater_disabled")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Data Updater is currently disabled. Dynamic data updates are not available.",
                )
        except Exception as e:
            logger.error(f"Error during data update: {str(e)}")
            if span is not None:
                span.set_status(trace.StatusCode.ERROR)
                span.set_attribute("error", True)
                span.record_exception(e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update data",
            )

    return router
