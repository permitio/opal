from fastapi import APIRouter, status
from starlette.status import HTTP_200_OK
from horizon.policy.updater import update_policy, update_policy_data

router = APIRouter()


@router.post("/update_policy", status_code=status.HTTP_200_OK)
async def trigger_policy_update():
    await update_policy(reason="request from sdk")
    return {"status": "ok"}

@router.post("/update_policy_data", status_code=status.HTTP_200_OK)
async def trigger_policy_data_update():
    await update_policy_data(reason="request from sdk")
    return {"status": "ok"}
