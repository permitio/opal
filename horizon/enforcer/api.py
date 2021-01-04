import json

from fastapi import APIRouter, status, Response
from starlette import responses
from horizon.enforcer.schemas import AuthorizationQuery
from horizon.enforcer.client import opa
from horizon.logger import get_logger

logger = get_logger("Enforcer")
router = APIRouter()


def log_query_and_result(query: AuthorizationQuery, response: Response):
    params = "({}, {}, {})".format(query.user, query.action, query.resource.type)
    try:
        result = bool(json.loads(response.body).get("result", False))
        logger.info(f"is allowed = {result}", params=params, query=query.dict())
    except:
        logger.info("is allowed", params=params, query=query.dict())


@router.post("/allowed", status_code=status.HTTP_200_OK)
async def is_allowed(query: AuthorizationQuery):
    response = await opa.is_allowed(query)
    log_query_and_result(query, response)
    return response

