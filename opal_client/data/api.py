from fastapi import APIRouter, status

from opal_common.logger import logger
from opal_client.data.updater import DataUpdater

def init_data_router(data_updater: DataUpdater):
    router = APIRouter()

    @router.post("/data-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_data_update():
        logger.info("triggered policy data update from api")
        await data_updater.get_base_policy_data(data_fetch_reason="request from sdk")
        return {"status": "ok"}

    return router
