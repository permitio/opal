import json
import os
import pathlib
from typing import Optional, List

import aiohttp
from fastapi import APIRouter, Path, status, Query, HTTPException, Header, Depends
from fastapi.security.utils import get_authorization_scheme_param
from fastapi_websocket_pubsub import PubSubEndpoint
from git import Repo
from pydantic import parse_obj_as

from opal_common.topics.publisher import ServerSideTopicPublisher
from opal_server.policy.bundles.api import make_bundle
from opal_server.policy.watcher.callbacks import publish_changed_directories
from opal_server.redis import RedisDB
from opal_server.scopes.pull_engine import CeleryPullEngine
from opal_server.scopes.pullers import InvalidScopeSourceType, create_puller
from opal_server.scopes.scope_store import ScopeStore, ScopeNotFound, \
    ReadOnlyScopeStore
from opal_common.git.bundle_maker import BundleMaker
from opal_server.config import opal_server_config
from opal_common.schemas.policy import PolicyBundle
from opal_common.scopes.scopes import ScopeConfig


async def preload_scopes():
    scope_store = ScopeStore(
        base_dir=opal_server_config.SCOPE_BASE_DIR,
        redis=RedisDB(opal_server_config.REDIS_URL)
    )

    headers = {
        'Authorization': f'Bearer {opal_server_config.SCOPE_API_KEY}'
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f'{opal_server_config.BACKEND_URL}/v1/scopes') as resp:
            resp_json = await resp.json()
            scopes = parse_obj_as(List[ScopeConfig], resp_json)

            for scope in scopes:
                await scope_store.add_scope(scope)


def setup_scopes_api(pubsub_endpoint: PubSubEndpoint):
    scope_store = ScopeStore(
        base_dir=opal_server_config.SCOPE_BASE_DIR,
        redis=opal_server_config.REDIS_URL
    )

    def _check_scope_api_key(authorization: Optional[str] = Header(None)):
        if not authorization:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

        scheme, param = get_authorization_scheme_param(authorization)

        if scheme.lower() != "bearer" or param != opal_server_config.SCOPE_API_KEY:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    router = APIRouter()

    @router.get("/scopes/{scope_id}", response_model=ScopeConfig, dependencies=[Depends(_check_scope_api_key)])
    async def get_scope(
        scope_id: str = Path(..., title="Scope ID"),
    ):
        try:
            scope = await scope_store.get_scope(scope_id)
            return scope.config
        except ScopeNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    @router.post("/scopes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_check_scope_api_key)])
    async def add_scope(
        scope_config: ScopeConfig
    ):
        try:
            await scope_store.add_scope(scope_config)
        except InvalidScopeSourceType as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Invalid scope source type: {e.invalid_type}'
            )
        except ReadOnlyScopeStore:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND
            )

    @router.get("/scopes/{scope_id}/bundle", response_model=PolicyBundle)
    async def get_bundle(
        scope_id: str = Path(..., title="Scope ID to be deleted"),
        base_hash: Optional[str] = Query(
            None, description="hash of previous bundle already downloaded, server will return a diff bundle.")
    ):
        scope = await scope_store.get_scope(scope_id)
        repo = Repo(os.path.join(opal_server_config.SCOPE_BASE_DIR, scope.location))

        bundle_maker = BundleMaker(
            repo,
            {pathlib.Path(p) for p in scope.config.policy.directories},
            extensions=opal_server_config.OPA_FILE_EXTENSIONS,
            manifest_filename=opal_server_config.POLICY_REPO_MANIFEST_PATH,
        )

        return make_bundle(bundle_maker, repo, base_hash)

    @router.post("/scopes/periodic-check", dependencies=[Depends(_check_scope_api_key)])
    async def periodic_check(
    ):
        scopes = await scope_store.all_scopes()

        for scope_id, scope in scopes:
            if not scope.config.policy.polling:
                continue

            puller = create_puller(Path(opal_server_config.SCOPE_BASE_DIR), scope.config)

            if puller.check():
                old_commit, new_commit = puller.diff()
                puller.pull()

                publisher = ServerSideTopicPublisher(
                    endpoint=pubsub_endpoint,
                    prefix=scope.config.scope_id
                )

                await publish_changed_directories(
                    old_commit=old_commit, new_commit=new_commit,
                    publisher=publisher
                )

    return router
