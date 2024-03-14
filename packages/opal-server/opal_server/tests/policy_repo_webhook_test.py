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
from opal_common.schemas.webhook import GitWebhookRequestParams
from opal_common.tests.test_utils import wait_for_server
from opal_server.policy.webhook.api import get_webhook_router, is_matching_webhook_url
from opal_server.policy.webhook.deps import (
    extracted_git_changes,
    validate_git_secret_or_throw_factory,
)

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
REPO_FULL_NAME = "permitio/opal"
REPO_URL = f"https://github.com/{REPO_FULL_NAME}"

# configure the server to work with a fake secret and our mock repository
SECRET = opal_server_config.POLICY_REPO_WEBHOOK_SECRET = "SECRET"
opal_server_config.POLICY_REPO_URL = REPO_URL


# Github mock example
GITHUB_WEBHOOK_BODY_SAMPLE = {
    "repository": {
        "id": 1296269,
        "url": REPO_URL,
        "full_name": REPO_FULL_NAME,
        "owner": {
            "login": "octocat",
            "id": 1,
        },
    },
}
SIGNATURE = hmac.new(
    SECRET.encode("utf-8"),
    json.dumps(GITHUB_WEBHOOK_BODY_SAMPLE).encode("utf-8"),
    hashlib.sha256,
).hexdigest()
GITHUB_WEBHOOK_HEADERS = {
    "X-GitHub-Event": "push",
    "X-Hub-Signature-256": f"sha256={SIGNATURE}",
}

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
    "X-Gitlab-Token": SECRET,
}

#######

# Azure GIT mock example
AZURE_GIT_WEBHOOK_BODY_SAMPLE = {
    "subscriptionId": "00000000-0000-0000-0000-000000000000",
    "notificationId": 48,
    "id": "03c164c2-8912-4d5e-8009-3707d5f83734",
    "eventType": "git.push",
    "publisherId": "tfs",
    "message": {
        "text": "user pushed updates to repo:master.",
    },
    "resource": {
        "commits": [
            {
                "commitId": "33b55f7cb7e7e245323987634f960cf4a6e6bc74",
                "author": {},
                "committer": {},
                "comment": "comment",
                "url": "https://org.visualstudio.com/DefaultCollection/_git/repo/commit/33b55f7cb7e7e245323987634f960cf4a6e6bc74",
            }
        ],
        "refUpdates": [
            {
                "name": "refs/heads/master",
                "oldObjectId": "111331d8d3b131fa9ae03cf5e53965b51942618a",
                "newObjectId": "11155f7cb7e7e245323987634f960cf4a6e6bc74",
            }
        ],
        "repository": {
            "id": "278d5cd2-584d-4b63-824a-2ba458937249",
            "name": "repo",
            "url": "https://org.visualstudio.com/DefaultCollection/_apis/git/repositories/111d5cd2-584d-4b63-824a-2ba458937249",
            "project": {
                "id": "111154b1-ce1f-45d1-b94d-e6bf2464ba2c",
                "name": "repo",
                "url": REPO_URL,
                "state": "wellFormed",
                "visibility": "unchanged",
                "lastUpdateTime": "0001-01-01T00:00:00",
            },
            "defaultBranch": "refs/heads/master",
            "remoteUrl": REPO_URL,
        },
        "pushedBy": {
            "displayName": "user",
            "id": "000@Live.com",
            "uniqueName": "user@hotmail.com",
        },
        "pushId": 14,
        "date": "2014-05-02T19:17:13.3309587Z",
        "url": "https://org.visualstudio.com/DefaultCollection/_apis/git/repositories/278d5cd2-584d-4b63-824a-2ba458937249/pushes/14",
    },
    "resourceVersion": "1.0",
    "resourceContainers": {},
    "createdDate": "2022-12-15T17:28:23.1937259Z",
}
AZURE_GIT_WEBHOOK_HEADERS = {
    "x-api-key": SECRET,
}

#######

# Bitbucket mock example
BITBUCKET_WEBHOOK_BODY_SAMPLE = {
    "repository": {
        "type": "repository",
        "full_name": REPO_FULL_NAME,
        "links": {},
        "uuid": "{58f3e7e4-9ca1-11ed-883d-5ab73abeaaed}",
    },
}

BITBUCKET_WEBHOOK_HEADERS = {
    "x-event-key": "repo:push",
    "x-hook-uuid": SECRET,
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

    validate_git_secret_or_throw = validate_git_secret_or_throw_factory(
        SECRET, webhook_config
    )

    webhook_router = get_webhook_router(
        [Depends(validate_git_secret_or_throw)],
        Depends(extracted_git_changes),
        PolicySourceTypes.Git,
        publish,
        webhook_config,
    )
    server_app.include_router(webhook_router)

    @server_app.on_event("startup")
    async def startup_event():
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
    proc = Process(
        target=setup_server,
        args=(event, opal_server_config.POLICY_REPO_WEBHOOK_PARAMS),
        daemon=True,
    )
    proc.start()
    assert event.wait(5)
    wait_for_server(PORT)
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
    assert event.wait(5)
    wait_for_server(PORT)
    yield event
    proc.kill()  # Cleanup after test


@pytest.fixture()
def azure_git_mode_server():
    # configure server in Azure-git mode
    webhook_config = GitWebhookRequestParams.parse_obj(
        {
            "secret_header_name": "x-api-key",
            "secret_type": "token",
            "secret_parsing_regex": "(.*)",
            "event_header_name": None,
            "event_request_key": "eventType",
            "push_event_value": "git.push",
        }
    )
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(event, webhook_config), daemon=True)
    proc.start()
    assert event.wait(5)
    wait_for_server(PORT)
    yield event
    proc.kill()  # Cleanup after test


@pytest.fixture()
def bitbucket_mode_server():
    # configure server in Azure-git mode
    webhook_config = GitWebhookRequestParams.parse_obj(
        {
            "secret_header_name": "x-hook-uuid",
            "secret_type": "token",
            "secret_parsing_regex": "(.*)",
            "event_header_name": "x-event-key",
            "event_request_key": None,
            "push_event_value": "repo:push",
        }
    )
    event = Event()
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(event, webhook_config), daemon=True)
    proc.start()
    assert event.wait(5)
    wait_for_server(PORT)
    yield event
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_webhook_mock_github(github_mode_server):
    """Test the webhook route simulating a webhook from Github."""
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


@pytest.mark.asyncio
async def test_webhook_mock_azure_git(azure_git_mode_server):
    """Test the webhook route simulating a webhook from Azure-Git."""
    # simulate a webhook
    async with ClientSession() as session:
        async with session.post(
            WEBHOOK_URL,
            data=json.dumps(AZURE_GIT_WEBHOOK_BODY_SAMPLE),
            headers=AZURE_GIT_WEBHOOK_HEADERS,
        ) as resp:
            pass
    # Use the special test route, to check that an event was published successfully
    async with ClientSession() as session:
        async with session.get(PUBLISHED_EVENTS_URL) as resp:
            json_body = await resp.json()
            assert "webhook" in json_body


@pytest.mark.asyncio
async def test_webhook_mock_bitbucket(bitbucket_mode_server):
    """Test the webhook route simulating a webhook from Azure-Git."""
    # simulate a webhook
    async with ClientSession() as session:
        async with session.post(
            WEBHOOK_URL,
            data=json.dumps(BITBUCKET_WEBHOOK_BODY_SAMPLE),
            headers=BITBUCKET_WEBHOOK_HEADERS,
        ) as resp:
            pass
    # Use the special test route, to check that an event was published successfully
    async with ClientSession() as session:
        async with session.get(PUBLISHED_EVENTS_URL) as resp:
            json_body = await resp.json()
            assert "webhook" in json_body


def test_webhook_url_matcher():
    url = "https://git.permit.io/opal/server"
    # these should all be equivalent to the above URL
    urls = [
        "https://user:pass@git.permit.io/opal/server",
        "https://user@git.permit.io/opal/server",
        "https://user@git.permit.io/opal/server?private=1",
    ]

    for test in urls:
        assert is_matching_webhook_url(test, [url], [])

    # These should not match
    urls = [
        "https://git.permit.io:9090/opal/server",
        "http://git.permit.io/opal/server",
        "https://git.permit.io/opal/client",
    ]

    for test in urls:
        assert not is_matching_webhook_url(test, [url], [])

    # These should match by repo name "opal/server"
    urls = [
        "https://user:pass@git.permit.io/opal/server",
        "https://user@git.permit.io/opal/server",
        "https://user@git.permit.io/opal/server?private=1",
        "https://git.permit.io:9090/opal/server",
        "http://git.permit.io/opal/server",
        "https://git.permit.io/opal/server.git",
    ]

    for test in urls:
        assert is_matching_webhook_url(test, [], ["opal/server"])

    # These should not match by repo name "opal/server"
    urls = [url.replace("server", "client") for url in urls]

    for test in urls:
        assert not is_matching_webhook_url(test, [], ["opal/server"])
