import hashlib
import hmac
from typing import List, Optional

from fastapi import Header, HTTPException, Request, status
from opal_server.config import opal_server_config


async def validate_github_signature_or_throw(
    request: Request, x_hub_signature_256: Optional[str] = Header(None)
) -> bool:
    """authenticates a request from github webhook system by checking that the
    request contains a valid signature (i.e: the secret stored on github)."""
    if opal_server_config.POLICY_REPO_WEBHOOK_SECRET is None:
        # webhook can be configured without secret (not recommended but quite possible)
        return True

    if x_hub_signature_256 is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="signature was not provided!",
        )

    payload = await request.body()
    our_signature = hmac.new(
        opal_server_config.POLICY_REPO_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # header is of the form `sha256={sig}`, we need only the `{sig}` part
    provided_signature = x_hub_signature_256.split("=")[1]
    if not hmac.compare_digest(our_signature, provided_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="signatures didn't match!"
        )

    return True


async def affected_repo_urls(request: Request) -> List[str]:
    """extracts the repo url from a webhook request payload.

    used to make sure that the webhook was triggered on *our* monitored
    repo.
    """
    payload = await request.json()
    repo_payload = payload.get("repository", {})
    git_url = repo_payload.get("git_url", None)
    ssh_url = repo_payload.get("ssh_url", None)
    clone_url = repo_payload.get("clone_url", None)

    # additional support for url payload
    git_http_url = repo_payload.get("git_ssh_url", None)
    ssh_http_url = repo_payload.get("git_http_url", None)
    url = repo_payload.get("url", None)

    urls = list(set([git_url, ssh_url, clone_url, git_http_url, ssh_http_url, url]))
    if not urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repo url not found in payload!",
        )
    return urls
