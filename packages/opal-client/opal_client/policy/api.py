from fastapi import APIRouter, status
from opal_client.policy.updater import PolicyUpdater
from opal_common.logger import logger


def init_policy_router(policy_updater: PolicyUpdater):
    router = APIRouter()

    @router.post("/policy-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_update():
        logger.info("triggered policy update from api")
        await policy_updater.update_policy(force_full_update=True)
        return {"status": "ok"}

    return router
