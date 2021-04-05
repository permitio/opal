from fastapi import APIRouter, status
from starlette.status import HTTP_200_OK

from opal_common.logger import logger
from opal_client.policy.updater import update_policy
from opal_client.policy_store import BasePolicyStoreClient, DEFAULT_POLICY_STORE_GETTER

def init_policy_router(policy_store:BasePolicyStoreClient=None):
    policy_store = policy_store or DEFAULT_POLICY_STORE_GETTER()
    router = APIRouter()

    @router.post("/policy-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_update():
        logger.info("triggered policy update from api")
        await update_policy(policy_store)
        return {"status": "ok"}

    return router
