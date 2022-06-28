import pathlib
from typing import Optional, cast

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from fastapi_websocket_pubsub import PubSubEndpoint
from opal_common.authentication.authz import (
    require_peer_type,
    restrict_optional_topics_to_publish,
)
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.schemas.data import DataSourceConfig, DataUpdate
from opal_common.schemas.policy import PolicyBundle, PolicyUpdateMessageNotification
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.schemas.scopes import Scope
from opal_common.schemas.security import PeerType
from opal_common.topics.publisher import ScopedServerSideTopicPublisher
from opal_server.config import opal_server_config
from opal_server.data.data_update_publisher import DataUpdatePublisher
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError, ScopeRepository


def init_scope_router(
    scopes: ScopeRepository, authenticator: JWTAuthenticator, pubsub: PubSubEndpoint
):
    router = APIRouter()

    def _allowed_scoped_authenticator(
        claims: JWTClaims = Depends(authenticator), scope_id: str = Path(...)
    ):
        if not authenticator.enabled:
            return

        allowed_scopes = claims.get("allowed_scopes")

        if not allowed_scopes or scope_id not in allowed_scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN)

    def _check_worker_token(authorization: str = Header()):
        if authorization is None:
            raise Unauthorized()

        scheme, token = authorization.split(" ")

        if scheme.lower() != "bearer" or token != opal_server_config.WORKER_TOKEN:
            raise Unauthorized()

    @router.put("", status_code=status.HTTP_201_CREATED)
    async def put_scope(*, scope_in: Scope, claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to PUT scope: {repr(ex)}")
            raise

        await scopes.put(scope_in)

        from opal_server.worker import sync_scope

        sync_scope.delay(scope_in.scope_id)

        return Response(status_code=status.HTTP_201_CREATED)

    @router.get(
        "/{scope_id}",
        response_model=Scope,
        response_model_exclude={"policy": {"auth"}},
    )
    async def get_scope(*, scope_id: str, claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to get scope: {repr(ex)}")
            raise

        try:
            scope = await scopes.get(scope_id)
            return scope
        except ScopeNotFoundError:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}"
            )

    @router.delete(
        "/{scope_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_scope(
        *, scope_id: str, claims: JWTClaims = Depends(authenticator)
    ):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to delete scope: {repr(ex)}")
            raise

        await scopes.delete(scope_id)

        from opal_server.worker import delete_scope

        delete_scope.delay(scope_id)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/{scope_id}/refresh", status_code=status.HTTP_200_OK)
    async def refresh_scope(scope_id: str, claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to delete scope: {repr(ex)}")
            raise

        try:
            _ = await scopes.get(scope_id)

            from opal_server.worker import sync_scope

            sync_scope.delay(scope_id)

            return Response(status_code=status.HTTP_200_OK)

        except ScopeNotFoundError:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}"
            )

    @router.get(
        "/{scope_id}/policy",
        response_model=PolicyBundle,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(_allowed_scoped_authenticator)],
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

        if isinstance(scope.policy, GitPolicyScopeSource):
            fetcher = GitPolicyFetcher(
                pathlib.Path(opal_server_config.BASE_DIR),
                scope.scope_id,
                cast(GitPolicyScopeSource, scope.policy),
            )

            bundle = fetcher.make_bundle(base_hash)
            return bundle

    @router.get(
        "/{scope_id}/data",
        response_model=DataSourceConfig,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(_allowed_scoped_authenticator)],
    )
    async def get_scope_data_config(*, scope_id: str = Path(..., title="Scope ID")):
        logger.info(
            "Serving source configuration for scope {scope_id}", scope_id=scope_id
        )
        scope = await scopes.get(scope_id)
        return scope.data

    @router.post(
        "/{scope_id}/policy/update",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(_check_worker_token)],
    )
    async def notify_new_policy(
        *,
        scope_id: str = Path(..., description="Scope ID"),
        notification: PolicyUpdateMessageNotification,
    ):
        async with ScopedServerSideTopicPublisher(pubsub, scope_id) as publisher:
            publisher.publish(notification.topics, notification.update)
            await publisher.wait()

    @router.post("/{scope_id}/data/update")
    async def publish_data_update_event(
        update: DataUpdate,
        claims: JWTClaims = Depends(authenticator),
        scope_id: str = Path(..., description="Scope ID"),
    ):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)

            restrict_optional_topics_to_publish(authenticator, claims, update)

            for entry in update.entries:
                entry.topics = [f"data:{topic}" for topic in entry.topics]

            async with ScopedServerSideTopicPublisher(pubsub, scope_id) as publisher:
                DataUpdatePublisher(publisher).publish_data_updates(update)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to publish update: {repr(ex)}")
            raise

    return router
