from typing import List

from fastapi import APIRouter, Depends, Request, status
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.logger import logger
from opal_server.config import PolicySourceTypes, opal_server_config
from opal_server.policy.webhook.deps import (
    affected_repo_urls,
    validate_github_signature_or_throw,
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
        route_dependency = validate_github_signature_or_throw
        func_dependency = affected_repo_urls

    router = APIRouter()

    @router.post(
        "/webhook",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(route_dependency)],
    )
    async def trigger_webhook(
        request: Request, urls: List[str] = Depends(func_dependency)
    ):
        # TODO: breaking change: change "repo_url" to "remote_url" in next major
        if source_type == PolicySourceTypes.Git:
            event = request.headers.get("X-GitHub-Event", "ping")

            if (
                opal_server_config.POLICY_REPO_URL is not None
                and opal_server_config.POLICY_REPO_URL in urls
            ):
                logger.info(
                    "triggered webhook on repo: {repo}",
                    repo=opal_server_config.POLICY_REPO_URL,
                    hook_event=event,
                )
                if event == "push":
                    # notifies the webhook listener via the pubsub broadcaster
                    await pubsub_endpoint.publish(
                        opal_server_config.POLICY_REPO_WEBHOOK_TOPIC
                    )
                return {
                    "status": "ok",
                    "event": event,
                    "repo_url": opal_server_config.POLICY_REPO_URL,
                }

        elif source_type == PolicySourceTypes.Api:
            logger.info("Triggered webhook to check API bundle URL")
            await pubsub_endpoint.publish(opal_server_config.POLICY_REPO_WEBHOOK_TOPIC)
            return {
                "status": "ok",
                "event": "webhook_trigger",
                "repo_url": opal_server_config.POLICY_BUNDLE_URL,
            }

        return {"status": "ignored", "event": event}

    return router
