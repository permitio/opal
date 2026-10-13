from typing import Callable, List
from urllib.parse import SplitResult, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.logger import logger
from opal_common.schemas.webhook import GitWebhookRequestParams
from opal_server.config import PolicySourceTypes, opal_server_config
from opal_server.policy.watcher.manifest import get_active_policy_bundle_sources
from opal_server.policy.watcher.task import policy_webhook_topic
from opal_server.policy.webhook.deps import (
    GitChanges,
    extracted_git_changes,
    validate_git_secret_or_throw,
)


def init_git_webhook_router(
    pubsub_endpoint: PubSubEndpoint, authenticator: JWTAuthenticator
):
    async def dummy_affected_repo_urls(request: Request) -> List[str]:
        return []

    source_type = opal_server_config.POLICY_SOURCE_TYPE
    if source_type == PolicySourceTypes.Api:
        route_dependency = authenticator
        func_dependency = dummy_affected_repo_urls
    else:
        route_dependency = validate_git_secret_or_throw
        func_dependency = extracted_git_changes

    return get_webhook_router(
        [Depends(route_dependency)],
        Depends(func_dependency),
        source_type,
        pubsub_endpoint.publish,
    )


def is_matching_webhook_url(input_url: str, urls: List[str], names: List[str]) -> bool:
    parsed = urlparse(input_url)
    netloc = parsed.hostname

    if parsed.port:
        netloc = f"{parsed.hostname}:{parsed.port}"

    normalized = SplitResult(
        scheme=parsed.scheme, netloc=netloc, path=parsed.path, query="", fragment=""
    )

    if urls:
        return str(normalized.geturl()) in urls
    else:
        repo_name_from_path = normalized.path.removeprefix("/").removesuffix(".git")
        return repo_name_from_path in names


def get_webhook_router(
    route_dependencies: List[Depends],
    git_changes: Depends,
    source_type: PolicySourceTypes,
    publish: Callable,
    webhook_config: GitWebhookRequestParams = opal_server_config.POLICY_REPO_WEBHOOK_PARAMS,
):
    if webhook_config is None:
        webhook_config = opal_server_config.POLICY_REPO_WEBHOOK_PARAMS
    router = APIRouter()

    @router.post(
        "/webhook",
        status_code=status.HTTP_200_OK,
        dependencies=route_dependencies,
    )
    async def trigger_webhook(request: Request, git_changes: GitChanges = git_changes):
        # TODO: breaking change: change "repo_url" to "remote_url" in next major
        if source_type == PolicySourceTypes.Git:
            # look at values extracted from request
            urls = git_changes.urls
            branch = git_changes.branch
            names = git_changes.names

            # Enforce branch matching (webhook to config) if turned on via config
            if (
                opal_server_config.POLICY_REPO_WEBHOOK_ENFORCE_BRANCH
                and opal_server_config.POLICY_REPO_MAIN_BRANCH != branch
            ):
                logger.warning(
                    "Git Webhook ignored - POLICY_REPO_WEBHOOK_ENFORCE_BRANCH is enabled, and POLICY_REPO_MAIN_BRANCH is `{tracking}` but received webhook for a different branch ({branch})",
                    tracking=opal_server_config.POLICY_REPO_MAIN_BRANCH,
                    branch=branch,
                )
                return None

            # parse event from header
            if webhook_config.event_header_name is not None:
                event = request.headers.get(webhook_config.event_header_name, "ping")
            # parse event from request body
            elif webhook_config.event_request_key is not None:
                payload = await request.json()
                event = payload.get(webhook_config.event_request_key, "ping")
            else:
                logger.error(
                    "Webhook config is missing both event_request_key and event_header_name. Must have at least one."
                )

            policy_repo_url = opal_server_config.POLICY_REPO_URL

            # Check if the URL we are tracking is mentioned in the webhook
            if policy_repo_url and (
                is_matching_webhook_url(policy_repo_url, urls, names)
                or not webhook_config.match_sender_url
            ):
                logger.info(
                    "triggered webhook on repo: {repo}",
                    repo=opal_server_config.POLICY_REPO_URL,
                    hook_event=event,
                )
                # Check if this it the right event (push)
                if event == webhook_config.push_event_value:
                    # notifies the webhook listener via the pubsub broadcaster
                    await publish(opal_server_config.POLICY_REPO_WEBHOOK_TOPIC)
                return {
                    "status": "ok",
                    "event": event,
                    "repo_url": opal_server_config.POLICY_REPO_URL,
                }
            else:
                logger.warning(
                    "Got an unexpected webhook not matching the tracked repo ({repo}) - with these URLS: {urls} and those names: {names}.",
                    repo=opal_server_config.POLICY_REPO_URL,
                    urls=urls,
                    names=names,
                    hook_event=event,
                )

        elif source_type == PolicySourceTypes.Api:
            try:
                sources = (await get_active_policy_bundle_sources()).sources
            except Exception as exc:
                logger.warning(
                    "Policy bundle source registry is unavailable "
                    "(error type: {error_type})",
                    error_type=type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="policy source registry is not ready",
                ) from exc
            source_id = request.query_params.get("source_id")
            if sources or opal_server_config.POLICY_BUNDLE_MANIFEST_URL:
                if source_id is None and len(sources) == 1:
                    source_id = sources[0].source_id
                if source_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="source_id is required when multiple API bundle sources are configured",
                    )
                source = next(
                    (item for item in sources if item.source_id == source_id), None
                )
                if source is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"unknown API bundle source: {source_id}",
                    )
                repo_url = source.url
                webhook_topic = (
                    opal_server_config.POLICY_REPO_WEBHOOK_TOPIC
                    if opal_server_config.POLICY_BUNDLE_MANIFEST_URL
                    else policy_webhook_topic(source_id)
                )
            else:
                if source_id is not None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"unknown API bundle source: {source_id}",
                    )
                repo_url = opal_server_config.POLICY_BUNDLE_URL
                webhook_topic = opal_server_config.POLICY_REPO_WEBHOOK_TOPIC

            logger.info(
                "Triggered webhook to check API bundle source: {source_id}",
                source_id=source_id,
            )
            if opal_server_config.POLICY_BUNDLE_MANIFEST_URL:
                await publish(webhook_topic, data={"source_id": source_id})
            else:
                await publish(webhook_topic)
            return {
                "status": "ok",
                "event": "webhook_trigger",
                "repo_url": repo_url,
                "source_id": source_id,
            }

        return {"status": "ignored", "event": event}

    return router
