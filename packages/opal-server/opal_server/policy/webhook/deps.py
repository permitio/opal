import hashlib
import hmac
import re
from typing import List, Optional

from fastapi import Header, HTTPException, Request, status
from opal_common.schemas.webhook import GitWebhookRequestParams, SecretTypeEnum
from opal_server.config import opal_server_config
from pydantic import BaseModel


def validate_git_secret_or_throw_factory(
    webhook_secret: Optional[str] = opal_server_config.POLICY_REPO_WEBHOOK_SECRET,
    webhook_params: GitWebhookRequestParams = opal_server_config.POLICY_REPO_WEBHOOK_PARAMS,
):
    """Factory function to create secret validator dependency according to
    config.

    Returns: validate_git_secret_or_throw (async function)

    Args:
        webhook_secret (Optional[ str ], optional): The secret to validate. Defaults to opal_server_config.POLICY_REPO_WEBHOOK_SECRET.
        webhook_params (GitWebhookRequestParams, optional):The webhook configuration - including how to parse the secret. Defaults to opal_server_config.POLICY_REPO_WEBHOOK_PARAMS.
    """

    async def validate_git_secret_or_throw(request: Request) -> bool:
        """Authenticates a request from a git service webhook system by
        checking that the request contains a valid signature (i.e: via the
        secret stored on github) or a valid token (as stored in Gitlab)."""
        if webhook_secret is None:
            # webhook can be configured without secret (not recommended but quite possible)
            return True

        # get the secret the git service has sent us
        incoming_secret = request.headers.get(webhook_params.secret_header_name, "")

        # parse out the actual secret (Some services like Github add prefixes)
        matches = re.findall(
            webhook_params.secret_parsing_regex,
            incoming_secret,
        )
        incoming_secret = matches[0] if len(matches) > 0 else None

        # check we actually got something
        if incoming_secret is None or len(incoming_secret) == 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No secret was provided!",
            )

        # Check secret as signature
        if webhook_params.secret_type == SecretTypeEnum.signature:
            # calculate our signature on the post body
            payload = await request.body()
            our_signature = hmac.new(
                webhook_secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()

            # compare signatures on the post body
            provided_signature = incoming_secret
            if not hmac.compare_digest(our_signature, provided_signature):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="signatures didn't match!",
                )
        # Check secret as token
        elif incoming_secret.encode("utf-8") != webhook_secret.encode("utf-8"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="secret-tokens didn't match!",
            )

        return True

    return validate_git_secret_or_throw


# Init with defaults
validate_git_secret_or_throw = validate_git_secret_or_throw_factory()


class GitChanges(BaseModel):
    """The summary of a webhook as the properties of what has changed on the
    reporting Git repo.

    urls - the affected repo URLS
    branch - the branch the event affected
    """

    urls: List[str] = []
    branch: Optional[str] = None
    names: List[str] = []


async def extracted_git_changes(request: Request) -> GitChanges:
    """Extracts the repo url from a webhook request payload.

    used to make sure that the webhook was triggered on *our* monitored
    repo.

    This functions search for common patterns for where the affected URL
    may appear in the webhook
    """
    payload = await request.json()

    ### --- Get branch ---  ###
    # Gitlab / gitHub style
    ref = payload.get("ref", None)

    # Azure style
    if ref is None:
        ref = payload.get("refUpdates", {}).get("name", None)

    if isinstance(ref, str):
        # remove prefix
        if ref.startswith("refs/heads/"):
            branch = ref[11:]
        else:
            branch = ref
    else:
        branch = None

    ### Get urls ###

    # Github style
    repo_payload = payload.get("repository", {})
    git_url = repo_payload.get("git_url", None)
    ssh_url = repo_payload.get("ssh_url", None)
    clone_url = repo_payload.get("clone_url", None)

    # Gitlab style
    project_payload = payload.get("project", {})
    project_git_http_url = project_payload.get("git_http_url", None)
    project_git_ssh_url = project_payload.get("git_ssh_url", None)
    project_full_name = project_payload.get("path_with_namespace", None)

    # Azure style
    resource_payload = payload.get("resource", {})
    azure_repo_payload = resource_payload.get("repository", {})
    remote_url = azure_repo_payload.get("remoteUrl", None)

    # Bitbucket+Github style for fullname
    full_name = repo_payload.get("full_name", None)

    # additional support for url payload
    git_http_url = repo_payload.get("git_ssh_url", None)
    ssh_http_url = repo_payload.get("git_http_url", None)
    url = repo_payload.get("url", None)

    # remove duplicates and None
    urls = list(
        set(
            [
                remote_url,
                git_url,
                ssh_url,
                clone_url,
                git_http_url,
                ssh_http_url,
                url,
                project_git_http_url,
                project_git_ssh_url,
            ]
        )
    )
    urls.remove(None)

    names = list(
        set(
            [
                project_full_name,
                full_name,
            ]
        )
    )
    names.remove(None)

    if not urls and not names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repo url or full name not found in payload!",
        )

    return GitChanges(urls=urls, branch=branch, names=names)
