import pathlib
from typing import List, Optional, cast

import pygit2
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
from fastapi.responses import RedirectResponse
from fastapi_websocket_pubsub import PubSubEndpoint
from git import InvalidGitRepositoryError
from opal_common.async_utils import run_sync
from opal_common.authentication.authz import (
    require_peer_type,
    restrict_optional_topics_to_publish,
)
from opal_common.authentication.casting import cast_private_key
from opal_common.authentication.deps import JWTAuthenticator, get_token_from_header
from opal_common.authentication.types import EncryptionKeyFormat, JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.data import (
    DataSourceConfig,
    DataUpdate,
    ServerDataSourceConfig,
)
from opal_common.schemas.policy import PolicyBundle, PolicyUpdateMessageNotification
from opal_common.schemas.policy_source import GitPolicyScopeSource, SSHAuthData
from opal_common.schemas.scopes import Scope
from opal_common.schemas.security import PeerType
from opal_common.topics.publisher import (
    ScopedServerSideTopicPublisher,
    ServerSideTopicPublisher,
)
from opal_common.urls import set_url_query_param
from opal_common.monitoring.prometheus_metrics import (
    opal_server_scope_request_count,
    opal_server_scope_request_latency,
    opal_server_scope_error_count,
    opal_server_scope_operation_count,
    opal_server_scope_data_update_latency,
    opal_server_scope_data_update_count,
    opal_server_scope_data_update_errors,
    opal_server_scope_policy_sync_latency,
    opal_server_scope_policy_sync_count
)
from opal_server.config import opal_server_config
from opal_server.data.data_update_publisher import DataUpdatePublisher
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError, ScopeRepository


def verify_private_key(private_key: str, key_format: EncryptionKeyFormat) -> bool:
    try:
        key = cast_private_key(private_key, key_format=key_format)
        return key is not None
    except Exception as e:
        return False


def verify_private_key_or_throw(scope_in: Scope):
    if isinstance(scope_in.policy.auth, SSHAuthData):
        auth = cast(SSHAuthData, scope_in.policy.auth)
        if not "\n" in auth.private_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "private key is expected to contain newlines!"},
            )

        is_pem_key = verify_private_key(
            auth.private_key, key_format=EncryptionKeyFormat.pem
        )
        is_ssh_key = verify_private_key(
            auth.private_key, key_format=EncryptionKeyFormat.ssh
        )
        if not (is_pem_key or is_ssh_key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "private key is invalid"},
            )


def init_scope_router(
    scopes: ScopeRepository,
    authenticator: JWTAuthenticator,
    pubsub_endpoint: PubSubEndpoint,
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

    @router.put("", status_code=status.HTTP_201_CREATED)
    async def put_scope(
        *,
        force_fetch: bool = Query(
            False,
            description="Whether the policy repo must be fetched from remote",
        ),
        scope_in: Scope,
        claims: JWTClaims = Depends(authenticator),
    ):
        opal_server_scope_request_count.labels(
            endpoint="put_scope", 
            method="PUT", 
            status="started"
        ).inc()
        with opal_server_scope_request_latency.labels(
            endpoint="put_scope", 
            method="PUT", 
            status="processing"
        ).time():
            try:
                require_peer_type(authenticator, claims, PeerType.datasource)
            except Unauthorized as ex:
                logger.error(f"Unauthorized to PUT scope: {repr(ex)}")
                opal_server_scope_error_count.labels(
                    scope_id=scope_in.scope_id, 
                    error_type="Unauthorized",
                    endpoint="put_scope"
                ).inc()
                raise

            verify_private_key_or_throw(scope_in)
            await scopes.put(scope_in)
            opal_server_scope_operation_count.labels(
                    operation="create", 
                    status="success"
                ).inc()

            force_fetch_str = " (force fetch)" if force_fetch else ""
            logger.info(f"Sync scope: {scope_in.scope_id}{force_fetch_str}")

            # All server replicas (leaders) should sync the scope.
            await pubsub_endpoint.publish(
                opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
                {"scope_id": scope_in.scope_id, "force_fetch": force_fetch},
            )

            return Response(status_code=status.HTTP_201_CREATED)

    @router.get(
        "",
        response_model=List[Scope],
        response_model_exclude={"policy": {"auth"}},
    )
    async def get_all_scopes(*, claims: JWTClaims = Depends(authenticator)):
        opal_server_scope_request_count.labels(
            endpoint="get_all_scopes", 
            method="GET", 
            status="started"
        ).inc()
        with opal_server_scope_request_latency.labels(
            endpoint="get_all_scopes", 
            method="GET", 
            status="processing"
        ).time():
            try:
                require_peer_type(authenticator, claims, PeerType.datasource)
            except Unauthorized as ex:
                logger.error(f"Unauthorized to get scopes: {repr(ex)}")
                opal_server_scope_error_count.labels(
                    scope_id="all_scopes",
                    error_type="Unauthorized",
                    endpoint="get_all_scopes"
                ).inc()
                raise
            opal_server_scope_operation_count.labels(
                operation="get_all",
                status="success"
            ).inc()
            return await scopes.all()

    @router.get(
        "/{scope_id}",
        response_model=Scope,
        response_model_exclude={"policy": {"auth"}},
    )
    async def get_scope(*, scope_id: str, claims: JWTClaims = Depends(authenticator)):
        opal_server_scope_request_count.labels(
            endpoint="get_scope",
            method="GET",
            status="started"
        ).inc()
        with opal_server_scope_request_latency.labels(
            endpoint="get_scope",
            method="GET",
            status="processing"
        ).time():
            try:
                require_peer_type(authenticator, claims, PeerType.datasource)
            except Unauthorized as ex:
                logger.error(f"Unauthorized to get scope: {repr(ex)}")
                opal_server_scope_error_count.labels(
                    scope_id=scope_id,
                    error_type="Unauthorized",
                    endpoint="get_scope"
                ).inc()
                raise

            try:
                scope = await scopes.get(scope_id)
                opal_server_scope_operation_count.labels(
                    operation="get",
                    status="success"
                ).inc()
                return scope
            except ScopeNotFoundError:
                opal_server_scope_error_count.labels(
                    scope_id=scope_id,
                    error_type="NotFound",
                    endpoint="get_scope"
                ).inc()
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
        opal_server_scope_request_count.labels(
            endpoint="delete_scope",
            method="DELETE",
            status="started"
        ).inc()
        with opal_server_scope_request_latency.labels(
            endpoint="delete_scope",
            method="DELETE",
            status="processing"
        ).time():
            try:
                require_peer_type(authenticator, claims, PeerType.datasource)
            except Unauthorized as ex:
                logger.error(f"Unauthorized to delete scope: {repr(ex)}")
                opal_server_scope_error_count.labels(
                    scope_id=scope_id,
                    error_type="Unauthorized",
                    endpoint="delete_scope"
                ).inc()
                raise

            # TODO: This should also asynchronously clean the repo from the disk (if it's not used by other scopes)
            await scopes.delete(scope_id)
            opal_server_scope_operation_count.labels(
                operation="delete", 
                status="success"
            ).inc()
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/{scope_id}/refresh", status_code=status.HTTP_200_OK)
    async def refresh_scope(
        scope_id: str,
        hinted_hash: Optional[str] = Query(
            None,
            description="Commit hash that should exist in the repo. "
            + "If the commit is missing from the local clone, OPAL "
            + "understands it as a hint that the repo should be fetched from remote.",
        ),
        claims: JWTClaims = Depends(authenticator),
    ):
        with opal_server_scope_policy_sync_latency.labels(scope_id=scope_id).time():
            try:
                require_peer_type(authenticator, claims, PeerType.datasource)
            except Unauthorized as ex:
                logger.error(f"Unauthorized to delete scope: {repr(ex)}")
                opal_server_scope_error_count.labels(scope_id=scope_id, error_type="Unauthorized").inc()
                raise

            try:
                _ = await scopes.get(scope_id)

                logger.info(f"Refresh scope: {scope_id}")

                # If the hinted hash is None, we have no way to know whether we should
                # re-fetch the remote, so we force fetch, just in case.
                force_fetch = hinted_hash is None

                # All server replicas (leaders) should sync the scope.
                await pubsub_endpoint.publish(
                    opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
                    {
                        "scope_id": scope_id,
                        "force_fetch": force_fetch,
                        "hinted_hash": hinted_hash,
                    },
                )
                opal_server_scope_policy_sync_count.labels(scope_id=scope_id).inc()
                return Response(status_code=status.HTTP_200_OK)

            except ScopeNotFoundError:
                opal_server_scope_error_count.labels(scope_id=scope_id, error_type="NotFound").inc()
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}"
                )

    @router.post("/refresh", status_code=status.HTTP_200_OK)
    async def sync_all_scopes(claims: JWTClaims = Depends(authenticator)):
        """sync all scopes."""
        opal_server_scope_request_count.labels(
            endpoint="sync_all_scopes", 
            method="POST", 
            status="started"
        ).inc()
        with opal_server_scope_request_latency.labels(
            endpoint="sync_all_scopes", 
            method="POST", 
            status="processing"
        ).time():
            try:
                require_peer_type(authenticator, claims, PeerType.datasource)
            except Unauthorized as ex:
                logger.error(f"Unauthorized to refresh all scopes: {repr(ex)}")
                opal_server_scope_error_count.labels(
                    scope_id="all_scopes",
                    error_type="Unauthorized",
                    endpoint="sync_all_scopes"
                ).inc()
                raise

            # All server replicas (leaders) should sync all scopes.
            await pubsub_endpoint.publish(opal_server_config.POLICY_REPO_WEBHOOK_TOPIC)
            opal_server_scope_operation_count.labels(
                operation="sync_all", 
                status="success"
            ).inc()
            return Response(status_code=status.HTTP_200_OK)

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
        try:
            scope = await scopes.get(scope_id)
        except ScopeNotFoundError:
            logger.warning(
                "Requested scope {scope_id} not found, returning default scope",
                scope_id=scope_id,
            )
            return await _generate_default_scope_bundle(scope_id)

        if not isinstance(scope.policy, GitPolicyScopeSource):
            raise HTTPException(
                status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"policy source is not yet implemented: {scope_id}",
            )

        fetcher = GitPolicyFetcher(
            pathlib.Path(opal_server_config.BASE_DIR),
            scope.scope_id,
            cast(GitPolicyScopeSource, scope.policy),
        )

        try:
            return await run_sync(fetcher.make_bundle, base_hash)
        except (InvalidGitRepositoryError, pygit2.GitError, ValueError):
            logger.warning(
                "Requested scope {scope_id} has invalid repo, returning default scope",
                scope_id=scope_id,
            )
            return await _generate_default_scope_bundle(scope_id)

    async def _generate_default_scope_bundle(scope_id: str) -> PolicyBundle:
        metrics.event(
            "ScopeNotFound",
            message=f"Scope {scope_id} not found. Serving default scope instead",
            tags={"scope_id": scope_id},
        )

        try:
            scope = await scopes.get("default")
            fetcher = GitPolicyFetcher(
                pathlib.Path(opal_server_config.BASE_DIR),
                scope.scope_id,
                cast(GitPolicyScopeSource, scope.policy),
            )
            return fetcher.make_bundle(None)
        except (
            ScopeNotFoundError,
            InvalidGitRepositoryError,
            pygit2.GitError,
            ValueError,
        ):
            raise ScopeNotFoundError(scope_id)

    @router.get(
        "/{scope_id}/data",
        response_model=DataSourceConfig,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(_allowed_scoped_authenticator)],
    )
    async def get_scope_data_config(
        *,
        scope_id: str = Path(..., title="Scope ID"),
        authorization: Optional[str] = Header(None),
    ):
        logger.info(
            "Serving source configuration for scope {scope_id}", scope_id=scope_id
        )
        try:
            scope = await scopes.get(scope_id)
            return scope.data
        except ScopeNotFoundError as ex:
            logger.warning(
                "Requested scope {scope_id} not found, returning OPAL_DATA_CONFIG_SOURCES",
                scope_id=scope_id,
            )
            try:
                config: ServerDataSourceConfig = opal_server_config.DATA_CONFIG_SOURCES

                if config.external_source_url:
                    url = str(config.external_source_url)
                    token = get_token_from_header(authorization)
                    redirect_url = set_url_query_param(url, "token", token)
                    return RedirectResponse(url=redirect_url)
                else:
                    return config.config
            except ScopeNotFoundError:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(ex))

    @router.post("/{scope_id}/data/update")
    async def publish_data_update_event(
        update: DataUpdate,
        claims: JWTClaims = Depends(authenticator),
        scope_id: str = Path(..., description="Scope ID"),
    ):
        with opal_server_scope_data_update_latency.labels(scope_id=scope_id).time():
            try:
                require_peer_type(authenticator, claims, PeerType.datasource)

                restrict_optional_topics_to_publish(authenticator, claims, update)

                for entry in update.entries:
                    entry.topics = [f"data:{topic}" for topic in entry.topics]

                await DataUpdatePublisher(
                    ScopedServerSideTopicPublisher(pubsub_endpoint, scope_id)
                ).publish_data_updates(update)

                opal_server_scope_data_update_count.labels(scope_id=scope_id).inc()
            except Unauthorized as ex:
                logger.error(f"Unauthorized to publish update: {repr(ex)}")
                opal_server_scope_data_update_errors.labels(scope_id=scope_id).inc()
                opal_server_scope_error_count.labels(
                    scope_id=scope_id,
                    error_type="UpdateFailed",
                    endpoint="data_update"
                ).inc()
                raise

    return router
