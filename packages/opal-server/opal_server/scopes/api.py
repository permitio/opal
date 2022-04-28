import os
import pathlib
from typing import Optional, List

import aiohttp
from fastapi import APIRouter, Path, status, Query, HTTPException, Header, Depends
from fastapi.security.utils import get_authorization_scheme_param
from fastapi_websocket_pubsub import PubSubEndpoint
from git import Repo
from pydantic import parse_obj_as

from opal_common.schemas.data import DataSourceConfig
from opal_common.schemas.scopes import Scope
from opal_common.topics.publisher import ServerSideTopicPublisher
from opal_server.policy.bundles.api import make_bundle
from opal_server.policy.watcher.callbacks import publish_changed_directories
from opal_server.redis import RedisDB
from opal_server.scopes.pullers import InvalidScopeSourceType, create_puller
from opal_server.scopes.scope_store import ScopeStore, ScopeNotFound
from opal_common.git.bundle_maker import BundleMaker
from opal_server.config import opal_server_config
from opal_common.schemas.policy import PolicyBundle


async def preload_scopes():
    """
    Pre-loads all scope data from backend (and clone git sources)
    before OPAL starts
    """
    scope_store = ScopeStore(
        base_dir=opal_server_config.SCOPE_BASE_DIR,
        redis=RedisDB(opal_server_config.REDIS_URL)
    )

    if opal_server_config.SCOPE_API_KEY == "":
        return

    headers = {
        'Authorization': f'Bearer {opal_server_config.SCOPE_API_KEY}'
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f'{opal_server_config.BACKEND_URL}/v1/scopes') as resp:
            resp_json = await resp.json()
            scopes = parse_obj_as(List[Scope], resp_json)

            for scope in scopes:
                await scope_store.add_scope(scope)


def setup_scopes_api(pubsub_endpoint: PubSubEndpoint):
    scope_store = ScopeStore(
        base_dir=opal_server_config.SCOPE_BASE_DIR,
        redis=RedisDB(opal_server_config.REDIS_URL)
    )

    def _check_scope_api_key(authorization: Optional[str] = Header(None)):
        if not authorization:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

        scheme, param = get_authorization_scheme_param(authorization)

        if scheme.lower() != "bearer" or param != opal_server_config.SCOPE_API_KEY:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    router = APIRouter()

    @router.get("/scopes/{scope_id}", response_model=Scope, dependencies=[Depends(_check_scope_api_key)])
    async def get_scope(
        scope_id: str = Path(..., title="Scope ID"),
    ):
        try:
            scope = await scope_store.get_scope(scope_id)
            return scope
        except ScopeNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    @router.post("/scopes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_check_scope_api_key)])
    async def add_scope(
        scope: Scope
    ):
        try:
            await scope_store.add_scope(scope)
        except InvalidScopeSourceType as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Invalid scope source type: {e.invalid_type}'
            )

    @router.get("/scopes/{scope_id}/policy", response_model=PolicyBundle)
    async def get_scope_policy(
        scope_id: str = Path(..., title="Scope ID"),
        base_hash: Optional[str] = Query(
            None, description="hash of previous bundle already downloaded, server will return a diff bundle.")
    ):
        scope = await scope_store.get_scope(scope_id)
        repo = Repo(os.path.join(opal_server_config.SCOPE_BASE_DIR, scope.scope_id))

        bundle_maker = BundleMaker(
            repo,
            {pathlib.Path(p) for p in scope.policy.directories},
            extensions=scope.policy.extensions,
            manifest_filename=scope.policy.manifest,
        )

        return make_bundle(bundle_maker, repo, base_hash)

    @router.get('/scopes/{scope_id}/data', response_model=DataSourceConfig)
    async def get_scope_data(
        scope_id: str = Path(..., title='Scope ID')
    ):
        scope = await scope_store.get_scope(scope_id)
        return scope.data

    @router.post("/scopes/periodic-check", dependencies=[Depends(_check_scope_api_key)])
    async def periodic_check(
    ):
        scopes = await scope_store.all_scopes()

        for scope_id, scope in scopes:
            if not scope.policy.polling:
                continue

            puller = create_puller(Path(opal_server_config.SCOPE_BASE_DIR), scope)

            if puller.check():
                old_commit, new_commit = puller.diff()
                puller.pull()

                publisher = ServerSideTopicPublisher(
                    endpoint=pubsub_endpoint,
                    prefix=scope.scope_id
                )

                await publish_changed_directories(
                    old_commit=old_commit, new_commit=new_commit,
                    publisher=publisher
                )

    return router
