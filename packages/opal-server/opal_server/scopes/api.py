import pathlib
from typing import Optional

from fastapi import APIRouter, Path, Depends, Response, status, Query
from git import Repo

from opal_server.policy.bundles.api import make_bundle
from opal_server.scopes.scope_store import ScopeStore, ScopeConfig
from opal_common.git.bundle_maker import BundleMaker
from opal_server.config import opal_server_config
from opal_common.schemas.policy import PolicyBundle


def setup_scopes_api():
    router = APIRouter()
    scopes = ScopeStore(base_dir="/Users/orishavit/scopes", writer=True)

    def get_scopes():
        return scopes

    @router.get("/scopes/{scope_id}", response_model=ScopeConfig)
    async def get_scope(
        response: Response,
        scope_id: str = Path(..., title="Scope ID"),
        scopes: ScopeStore = Depends(get_scopes)
    ):
        try:
            return scopes.get_scope(scope_id)
        except KeyError:
            response.status_code = status.HTTP_404_NOT_FOUND

    @router.post("/scopes", status_code=status.HTTP_201_CREATED)
    async def add_scope(
        response: Response,
        scope_config: ScopeConfig,
        scopes: ScopeStore = Depends(get_scopes)
    ):
        scopes.add_scope(scope_config)

    @router.delete("/scopes/{scope_id}")
    async def delete_scope(
        response: Response,
        scope_id: str = Path(..., title="Scope ID to be deleted"),
        scopes: ScopeStore = Depends(get_scopes),
    ):
        try:
            scopes.delete_scope(scope_id)
        except KeyError:
            response.status_code = status.HTTP_404_NOT_FOUND

    @router.get("/scopes/{scope_id}/bundle", response_model=PolicyBundle)
    async def get_bundle(
        scope_id: str = Path(..., title="Scope ID to be deleted"),
        scopes: ScopeStore = Depends(get_scopes),
        base_hash: Optional[str] = Query(
            None, description="hash of previous bundle already downloaded, server will return a diff bundle.")
    ):
        scope = scopes.get_scope(scope_id)
        repository = scope.repository

        bundle_maker = BundleMaker(
            Repo(repository.path),
            {pathlib.Path(".")},
            extensions=opal_server_config.OPA_FILE_EXTENSIONS,
            manifest_filename=opal_server_config.POLICY_REPO_MANIFEST_PATH,
        )

        return make_bundle(bundle_maker, Repo(repository.path), base_hash)

    return router
