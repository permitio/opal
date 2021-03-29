from fastapi import APIRouter, status
from starlette.status import HTTP_200_OK
from opal_client.data.updater import update_policy_data

router = APIRouter()


@router.post("/data-updater/trigger", status_code=status.HTTP_200_OK)
async def trigger_policy_data_update():
    await update_policy_data(reason="request from sdk")
    return {"status": "ok"}
