from typing import Optional

from fastapi import APIRouter, HTTPException, status
from opal_client.data.updater import DataUpdater
from opal_common.logger import logger


def init_data_router(data_updater: Optional[DataUpdater]):
    router = APIRouter()

    @router.post("/data-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_data_update():
        logger.info("triggered policy data update from api")
        if data_updater:
            await data_updater.get_base_policy_data(
                data_fetch_reason="request from sdk"
            )
            return {"status": "ok"}
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Data Updater is currently disabled. Dynamic data updates are not available.",
            )

    return router
