from typing import Optional

from fastapi import APIRouter, HTTPException, status
from opal_client.data.updater import DataUpdater
from opal_common.logger import logger
from opal_common.monitoring.prometheus_metrics import (
    opal_client_data_update_trigger_count,
    opal_client_data_update_latency,
    opal_client_data_update_errors
)

def init_data_router(data_updater: Optional[DataUpdater]):
    router = APIRouter()

    @router.post("/data-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_data_update():
        logger.info("triggered policy data update from api")
        opal_client_data_update_trigger_count.labels(
            source="api",
            status="started"
        ).inc()
        try:
            if data_updater:
                with opal_client_data_update_latency.labels(source="api").time():
                    await data_updater.get_base_policy_data(
                        data_fetch_reason="request from sdk"
                    )
                    opal_client_data_update_trigger_count.labels(
                        source="api",
                        status="success"
                    ).inc()
                    return {"status": "ok"}
            else:
                opal_client_data_update_errors.labels(
                    error_type="updater_disabled",
                    source="api"
                ).inc()
                opal_client_data_update_trigger_count.labels(
                    source="api",
                    status="error"
                ).inc()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Data Updater is currently disabled. Dynamic data updates are not available.",
                )
        except Exception as e:
            opal_client_data_update_errors.labels(
                error_type="unknown",
                source="api"
            ).inc()
            logger.error(f"Error during data update: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update data"
            )
    return router
