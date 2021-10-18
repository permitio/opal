from typing import List

from fastapi import APIRouter, status, Request, Depends, status
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.logger import logger
from opal_server.config import PolicySourceTypes, opal_server_config
from opal_server.policy.webhook.deps import validate_github_signature_or_throw, affected_repo_urls


def init_git_webhook_router(pubsub_endpoint: PubSubEndpoint, authenticator: JWTAuthenticator):
    router = APIRouter()
    source_type = opal_server_config.POLICY_SOURCE_TYPE
    if source_type == PolicySourceTypes.Api:
        route_dependency = authenticator
        func_dependency = []
    else:
        route_dependency = validate_github_signature_or_throw
        func_dependency = affected_repo_urls

    @router.post(
        "/webhook",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(route_dependency)]
    )
    async def trigger_webhook(
        request: Request,
        urls: List[str] = Depends(func_dependency)
    ):
        event = request.headers.get('X-GitHub-Event', 'ping')

        if (opal_server_config.POLICY_REPO_URL is not None and opal_server_config.POLICY_REPO_URL in urls)\
                or \
                (source_type == PolicySourceTypes.Api):
            if source_type == PolicySourceTypes.Api:
                logger.info("Triggered webhook to check API bundle URL")
                response = {"status": "ok", "remote": opal_server_config.POLICY_BUNDLE_URL}
            elif source_type == PolicySourceTypes.Git:
                logger.info("triggered webhook on repo: {repo}", repo=urls[0], hook_event=event)
                response = {"status": "ok", "event": event, "repo_url": urls[0]}
            if event == 'push' or source_type == PolicySourceTypes.Api:
                # notifies the webhook listener via the pubsub broadcaster
                await pubsub_endpoint.publish(opal_server_config.POLICY_REPO_WEBHOOK_TOPIC)
            return response

        return {"status": "ignored", "event": event}
    return router

