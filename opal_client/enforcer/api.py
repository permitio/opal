import json

from fastapi import APIRouter, status, Response
from opal_client.enforcer.schemas import AuthorizationQuery, AuthorizationResult
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.logger import logger


def init_enforcer_api_router(policy_store:BasePolicyStoreClient):
    router = APIRouter()

    def log_query_and_result(query: AuthorizationQuery, response: Response):
        params = "({}, {}, {})".format(query.user, query.action, query.resource.type)
        try:
            result = json.loads(response.body).get("result", {})
            allowed = result.get("allow", False)
            permission = None
            granting_role = None
            if allowed:
                granting_permissions = result.get("granting_permission", [])
                granting_permission = {} if len(granting_permissions) == 0 else granting_permissions[0]
                permission = granting_permission.get("permission", {})
                granting_role = granting_permission.get("granting_role", None)
                if granting_role:
                    role_id = granting_role.get("id", "__NO_ID__")
                    roles = [r for r in result.get("user_roles", []) if r.get("id", "") == role_id]
                    granting_role = granting_role if not roles else roles[0]

            debug = {
                "opa_warnings": result.get("debug", []),
                "opa_processed_input": result.get("authorization_query", {}),
            }
            if allowed and permission is not None and granting_role is not None:
                debug["opa_granting_permision"] = permission
                debug["opa_granting_role"] = granting_role
            logger.info(f"is allowed = {allowed}", api_params=params, input=query.dict(), **debug)
        except:
            try:
                body = str(response.body, "utf-8")
            except:
                body = None
            data = {} if body is None else {"response_body" : body}
            logger.info("is allowed",
                params=params,
                query=query.dict(),
                response_status=response.status_code,
                **data
            )


    @router.post("/allowed", response_model=AuthorizationResult, status_code=status.HTTP_200_OK, response_model_exclude_none=True)
    async def is_allowed(query: AuthorizationQuery):
        response = await policy_store.is_allowed(query)
        log_query_and_result(query, response)
        try:
            raw_result = json.loads(response.body).get("result", {})
            processed_query = raw_result.get("authorization_query", {})
            result = {
                "allow": raw_result.get("allow", False),
                "result": raw_result.get("allow", False), # fallback for older sdks (TODO: remove)
                "query": {
                    "user": processed_query.get("user", {"id": query.user}),
                    "action": processed_query.get("action", query.action),
                    "resource": processed_query.get("resource", query.resource.dict()),
                },
                "debug": {
                    "warnings": raw_result.get("debug", []),
                    "user_roles": raw_result.get("user_roles", []),
                    "granting_permission": raw_result.get("granting_permission", []),
                    "user_permissions": raw_result.get("user_permissions", []),
                }
            }
        except:
            result = dict(allow=False, result=False)
            logger.warning("is allowed (fallback response)", reason="cannot decode opa response")
        return result

    return router

