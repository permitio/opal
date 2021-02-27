import hashlib
import hmac
from typing import Optional, List

from fastapi import APIRouter, status, Request, Depends, Header, HTTPException, status
from opal.common.logger import get_logger
from opal.server.config import POLICY_REPO_WEBHOOK_SECRET, POLICY_REPO_URL
from opal.server.gitwatcher.watcher import policy_watcher

logger = get_logger('Git Webhook')

async def validate_github_signature(request: Request, x_hub_signature_256: Optional[str] = Header(None)) -> bool:
    if POLICY_REPO_WEBHOOK_SECRET is None:
        # webhook can be configured without secret (not recommended but quite possible)
        return True

    if x_hub_signature_256 is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="signature was not provided!")

    payload = await request.body()
    our_signature = hmac.new(POLICY_REPO_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    # header is of the form `sha256={sig}`, we need only the `{sig}` part
    provided_signature = x_hub_signature_256.split('=')[1]
    if not hmac.compare_digest(our_signature, provided_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="signatures didn't match!")

    return True


router = APIRouter()

async def affected_repo_urls(request: Request) -> List[str]:
    payload = await request.json()
    repo_payload = payload.get("repository", {})
    git_url = repo_payload.get("git_url", None)
    ssh_url = repo_payload.get("ssh_url", None)
    clone_url = repo_payload.get("clone_url", None)
    urls = list(set([git_url, ssh_url, clone_url]))
    if not urls:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo url not found in payload!")
    return urls

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def trigger_git_webhook(request: Request, urls: List[str] = Depends(affected_repo_urls), verified: bool = Depends(validate_github_signature)):
    event = request.headers.get('X-GitHub-Event', 'ping')

    if POLICY_REPO_URL is not None and POLICY_REPO_URL in urls:
        logger.info("triggered webhook", repo=urls[0], hook_event=event)
        if event == 'push':
            policy_watcher.trigger()
        return { "status": "ok", "event": event, "repo_url": urls[0] }

    return { "status": "ignored", "event": event }