from fastapi import APIRouter, HTTPException, Response
from fastapi import status

from opal_common.schemas.scopes import Scope
from opal_server.scopes.scope_repository import ScopeRepository, ScopeNotFoundError


def init_scope_router(scopes: ScopeRepository):
    router = APIRouter()

    @router.put("", status_code=status.HTTP_201_CREATED)
    async def put_scope(
        *,
        scope_in: Scope
    ):
        await scopes.put(scope_in)

        from opal_server.worker import sync_scope
        sync_scope.delay(scope_in.scope_id)

        return Response(status_code=status.HTTP_201_CREATED)

    @router.get("/{scope_id}", response_model=Scope, response_model_exclude={"policy": {"auth"}})
    async def get_scope(
        *,
        scope_id: str
    ):
        try:
            scope = await scopes.get(scope_id)
            return scope
        except ScopeNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}")

    @router.delete("/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_scope(
        *,
        scope_id: str
    ):
        await scopes.delete(scope_id)

        from opal_server.worker import delete_scope
        delete_scope.delay(scope_id)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
