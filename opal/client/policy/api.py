from fastapi import APIRouter, status
from starlette.status import HTTP_200_OK
from opal.client.policy.updater import update_policy

router = APIRouter()


@router.post("/policy-updater/trigger", status_code=status.HTTP_200_OK)
async def trigger_policy_update():
    await update_policy(reason="request from sdk")
    return {"status": "ok"}
