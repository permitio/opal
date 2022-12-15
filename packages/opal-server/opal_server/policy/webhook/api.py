from typing import Callable, List

from fastapi import APIRouter, Depends, Request, status
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.logger import logger
from opal_common.schemas.webhook import GitWebhookRequestParams
from opal_server.config import PolicySourceTypes, opal_server_config
from opal_server.policy.webhook.deps import (
    affected_repo_urls,
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
        func_dependency = affected_repo_urls

    return get_webhook_router(
        [Depends(route_dependency)],
        Depends(func_dependency),
        source_type,
        pubsub_endpoint.publish,
    )


def get_webhook_router(
    route_dependencies: List[Depends],
    parse_urls: Depends,
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
    async def trigger_webhook(request: Request, urls: List[str] = parse_urls):
        # TODO: breaking change: change "repo_url" to "remote_url" in next major
        if source_type == PolicySourceTypes.Git:
            event = request.headers.get(webhook_config.event_header_name, "ping")

            # Check if the URL we are tracking is mentioned in the webhook
            if (
                opal_server_config.POLICY_REPO_URL is not None
                and opal_server_config.POLICY_REPO_URL in urls
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
                    "Got an unexpected webhook not matching the tracked repo ({repo}) - with these URLS instead: {urls} .",
                    repo=opal_server_config.POLICY_REPO_URL,
                    urls=urls,
                    hook_event=event,
                )

        elif source_type == PolicySourceTypes.Api:
            logger.info("Triggered webhook to check API bundle URL")
            await publish(opal_server_config.POLICY_REPO_WEBHOOK_TOPIC)
            return {
                "status": "ok",
                "event": "webhook_trigger",
                "repo_url": opal_server_config.POLICY_BUNDLE_URL,
            }

        return {"status": "ignored", "event": event}

    return router
