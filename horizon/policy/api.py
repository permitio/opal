from fastapi import APIRouter, status
from starlette.status import HTTP_200_OK
from horizon.policy.fetcher import policy_fetcher

router = APIRouter()


@router.post("/update_policy", status_code=status.HTTP_200_OK)
async def update_policy():
    await policy_fetcher.fetch_policy()
    return {"status": "ok"}

@router.post("/update_policy_data", status_code=status.HTTP_200_OK)
async def update_policy_data():
    await policy_fetcher.fetch_policy_data()
    return {"status": "ok"}
