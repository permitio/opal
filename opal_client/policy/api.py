from fastapi import APIRouter, status
from starlette.status import HTTP_200_OK
from opal_client.policy.updater import update_policy
from opal_client.policy_store import BasePolicyStoreClient, DEFAULT_POLICY_STORE

def init_policy_router(policy_store:BasePolicyStoreClient=DEFAULT_POLICY_STORE):
    router = APIRouter()

    @router.post("/policy-updater/trigger", status_code=status.HTTP_200_OK)
    async def trigger_policy_update():
        await update_policy(policy_store, reason="triggered by client api")
        return {"status": "ok"}

    return router
