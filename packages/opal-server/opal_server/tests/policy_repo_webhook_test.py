import asyncio
import hashlib
import hmac
import json
import os
import sys
from multiprocessing import Event, Process

import pytest
import uvicorn
from aiohttp import ClientSession
from fastapi import Depends
from fastapi_websocket_pubsub import PubSubClient
from flaky import flaky
from opal_common.schemas.webhook import GitWebhookRequestParams
from opal_server.policy.webhook.api import get_webhook_router
from opal_server.policy.webhook.deps import affected_repo_urls

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)


from opal_common.utils import get_authorization_header
from opal_server.config import PolicySourceTypes, opal_server_config

PORT = int(os.environ.get("PORT") or "9123")

# Basic server route config
WEBHOOK_ROUTE = "/webhook"
WEBHOOK_URL = f"http://localhost:{PORT}{WEBHOOK_ROUTE}"


# Check what got published on the server following our webhook
PUBLISHED_EVENTS_ROUTE = "/test-webhook-published-events"
PUBLISHED_EVENTS_URL = f"http://localhost:{PORT}{PUBLISHED_EVENTS_ROUTE}"

# mock tracked repo url
REPO_URL = "https://github.com/permitio/opal"

# configure the server to work with a fake secret and our mock repository
opal_server_config.POLICY_REPO_WEBHOOK_SECRET = "SECRET"
opal_server_config.POLICY_REPO_URL = REPO_URL


# Github mock example
GITHUB_WEBHOOK_BODY_SAMPLE = {
    "repository": {
        "id": 1296269,
        "url": REPO_URL,
        "full_name": "permitio/opal",
        "owner": {
            "login": "octocat",
            "id": 1,
        },
    },
}
SIGNATURE = hmac.new(
    opal_server_config.POLICY_REPO_WEBHOOK_SECRET.encode("utf-8"),
    json.dumps(GITHUB_WEBHOOK_BODY_SAMPLE).encode("utf-8"),
    hashlib.sha256,
).hexdigest()
GITHUB_WEBHOOK_HEADERS = {"X-GitHub-Event": "push", "X-Hub-Signature-256": SIGNATURE}

#######

# Gitlab mock example
GITLAB_WEBHOOK_BODY_SAMPLE = {
    "object_kind": "push",
    "event_name": "push",
    "before": "b93a4d411586dd541d5db230060378c58349875f",
    "after": "b28105e77c5a989a1502ca07af7a4487e3157470",
    "ref": "refs/heads/master",
    "checkout_sha": "b28105e77c5a989a1502ca07af7a4487e3157470",
    "message": None,
    "user_id": 1111111,
    "user_name": "First Last",
    "user_username": "username",
    "user_email": "",
    "user_avatar": "user_avatar",
    "project_id": 1111111,
    "project": {
        "id": 1111111,
        "name": "project",
        "description": None,
        "web_url": "web_url",
        "avatar_url": None,
        "git_ssh_url": "git@gitlab.com:user/project.git",
        "git_http_url": REPO_URL,
        "namespace": "username",
        "visibility_level": 0,
        "path_with_namespace": "username/project",
        "default_branch": "main",
        "ci_config_path": "",
        "homepage": "homepage",
        "url": "url",
        "ssh_url": "ssh_url",
        "http_url": "http_url",
    },
    "commits": [
        {
            "id": "commit_id",
            "message": "Send webhook event\n",
            "title": "Send webhook event",
            "timestamp": "2022-12-08T16:12:52+01:00",
            "url": "https://gitlab.com/user/project/-/commit/commit_id",
            "author": ["Object"],
            "added": [],
            "modified": ["Array"],
            "removed": [],
        }
    ],
    "total_commits_count": 1,
    "push_options": {},
    "repository": {
        "name": "Project",
        "url": "git@gitlab.com:user/project.git",
        "description": None,
        "homepage": "homepage",
        "git_http_url": "git_http_url",
        "git_ssh_url": "git_ssh_url",
        "visibility_level": 0,
    },
}
GITLAB_WEBHOOK_HEADERS = {
    "X-Gitlab-Event": "Push Hook",
    "X-Gitlab-Token": opal_server_config.POLICY_REPO_WEBHOOK_SECRET,
}


def setup_server(event, webhook_config):
    """
    Args:
        event: the event to indicate server readiness
        webhook_config: the configuration of the server for handling webhooks (e.g. github or gitlab)
    """
    from fastapi import FastAPI

    server_app = FastAPI()

    events = []

    async def publish(event):
        events.append(event)

    webhook_router = get_webhook_router(
        None,
        Depends(affected_repo_urls),
        PolicySourceTypes.Git,
        publish,
        webhook_config,
    )
    server_app.include_router(webhook_router)

    @server_app.on_event("startup")
    async def startup_event():
        await asyncio.sleep(0.4)
        # signal the server is ready
        event.set()

    @server_app.get(PUBLISHED_EVENTS_ROUTE)
    async def get_published_events():
        return events

    uvicorn.run(server_app, port=PORT)


@pytest.fixture()
def github_mode_server():
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(event, None), daemon=True)
    proc.start()
    yield event
    proc.kill()  # Cleanup after test


@pytest.fixture()
def gitlab_mode_server():
    # configure server in Gitlab mode
    webhook_config = GitWebhookRequestParams.parse_obj(
        {
            "secret_header_name": "X-Gitlab-Token",
            "secret_type": "token",
            "secret_parsing_regex": "(.*)",
            "event_header_name": "X-Gitlab-Event",
            "push_event_value": "Push Hook",
        }
    )
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(event, webhook_config), daemon=True)
    proc.start()
    yield event
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_webhook_mock_github(github_mode_server):
    """Test the webhook route simulating a webhook from Github."""
    # Wait for server to be ready
    github_mode_server.wait(5)
    # simulate a webhook
    async with ClientSession() as session:
        async with session.post(
            WEBHOOK_URL,
            data=json.dumps(GITHUB_WEBHOOK_BODY_SAMPLE),
            headers=GITHUB_WEBHOOK_HEADERS,
        ) as resp:
            pass
    # Use the special test route, to check that an event was published successfully
    async with ClientSession() as session:
        async with session.get(PUBLISHED_EVENTS_URL) as resp:
            json_body = await resp.json()
            assert "webhook" in json_body


@pytest.mark.asyncio
async def test_webhook_mock_gitlab(gitlab_mode_server):
    """Test the webhook route simulating a webhook from Gitlab."""
    # Wait for server to be ready
    gitlab_mode_server.wait(5)
    # simulate a webhook
    async with ClientSession() as session:
        async with session.post(
            WEBHOOK_URL,
            data=json.dumps(GITLAB_WEBHOOK_BODY_SAMPLE),
            headers=GITLAB_WEBHOOK_HEADERS,
        ) as resp:
            pass
    # Use the special test route, to check that an event was published successfully
    async with ClientSession() as session:
        async with session.get(PUBLISHED_EVENTS_URL) as resp:
            json_body = await resp.json()
            assert "webhook" in json_body
