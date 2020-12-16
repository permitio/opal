from fastapi import APIRouter, status
from horizon.enforcer.schemas import AuthorizationQuery
from horizon.enforcer.client import opa

router = APIRouter()


@router.post("/allowed", status_code=status.HTTP_200_OK)
async def is_allowed(query: AuthorizationQuery):
    return await opa.is_allowed(query)
