from typing import Optional, cast

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from opal_common.schemas.data import DataSourceConfig
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicySource
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import BadCommitError, GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError, ScopeRepository


def init_scope_router(scopes: ScopeRepository):
    router = APIRouter()

    @router.put("", status_code=status.HTTP_201_CREATED)
    async def put_scope(*, scope_in: Scope):
        await scopes.put(scope_in)

        from opal_server.worker import sync_scope

        sync_scope.delay(scope_in.scope_id)

        return Response(status_code=status.HTTP_201_CREATED)

    @router.get(
        "/{scope_id}", response_model=Scope, response_model_exclude={"policy": {"auth"}}
    )
    async def get_scope(*, scope_id: str):
        try:
            scope = await scopes.get(scope_id)
            return scope
        except ScopeNotFoundError:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}"
            )

    @router.delete("/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_scope(*, scope_id: str):
        await scopes.delete(scope_id)

        from opal_server.worker import delete_scope

        delete_scope.delay(scope_id)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/{scope_id}/policy",
        response_model=PolicyBundle,
        status_code=status.HTTP_200_OK,
    )
    async def get_scope_policy(
        *,
        scope_id: str = Path(..., title="Scope ID"),
        base_hash: Optional[str] = Query(
            None,
            description="hash of previous bundle already downloaded, server will return a diff bundle.",
        ),
    ):
        scope = await scopes.get(scope_id)

        if isinstance(scope.policy, GitPolicySource):
            fetcher = GitPolicyFetcher(
                opal_server_config.BASE_DIR,
                scope.scope_id,
                cast(GitPolicySource, scope.policy),
            )

            try:
                bundle = fetcher.make_bundle(base_hash)
                return bundle
            except BadCommitError as ex:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"commit with hash {ex.commit} was not found in the policy repo!",
                )

    return router
