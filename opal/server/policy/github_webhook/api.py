from typing import List

from fastapi import APIRouter, status, Request, Depends, status
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal.common.logger import logger
from opal.server.config import POLICY_REPO_URL, POLICY_REPO_WEBHOOK_TOPIC
from opal.server.policy.github_webhook.deps import validate_github_signature_or_throw, affected_repo_urls

def init_git_webhook_router(pubsub_endpoint: PubSubEndpoint):
    router = APIRouter()

    @router.post(
        "/webhook",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(validate_github_signature_or_throw)]
    )
    async def trigger_git_webhook(
        request: Request,
        urls: List[str] = Depends(affected_repo_urls)
    ):
        event = request.headers.get('X-GitHub-Event', 'ping')

        if POLICY_REPO_URL is not None and POLICY_REPO_URL in urls:
            logger.info("triggered webhook on repo: {repo}", repo=urls[0], hook_event=event)
            if event == 'push':
                # notifies the webhook listener via the pubsub broadcaster
                await pubsub_endpoint.publish(POLICY_REPO_WEBHOOK_TOPIC)
            return { "status": "ok", "event": event, "repo_url": urls[0] }

        return { "status": "ignored", "event": event }
    return router

