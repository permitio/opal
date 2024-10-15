import os
import json
import pytest
from testcontainers.core.generic import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

# https://stackoverflow.com/questions/7119452/git-commit-from-python


@pytest.fixture
def broadcast_channel():
    with PostgresContainer("postgres:14.1-alpine", driver=None) as postgres:
        yield postgres


@pytest.fixture(autouse=True)
def opal_server(broadcast_channel: PostgresContainer):
    environment = {
        "OPAL_BROADCAST_URI": broadcast_channel.get_connection_url(),
        "UVICORN_NUM_WORKERS": "4",
        "OPAL_POLICY_REPO_URL": os.getenv(
            "OPAL_POLICY_REPO_URL", "git@github.com:permitio/opal-tests-policy-repo.git"
        ),
        "OPAL_POLICY_REPO_SSH_KEY": os.getenv("OPAL_POLICY_REPO_SSH_KEY", ""),
        "OPAL_POLICY_REPO_MAIN_BRANCH": os.getenv("POLICY_REPO_BRANCH", "main"),
        "OPAL_POLICY_REPO_POLLING_INTERVAL": "30",
        "OPAL_DATA_CONFIG_SOURCES": json.dumps(
            {
                "config": {
                    "entries": [
                        {
                            # TODO: Replace this
                            "url": "http://localhost:7002/policy-data",
                            # "config": {
                            #     "headers": {
                            #         "Authorization": f"Bearer {os.getenv('OPAL_CLIENT_TOKEN', '')}"
                            #     }
                            # },
                            "topics": ["policy_data"],
                            "dst_path": "/static",
                        }
                    ]
                }
            }
        ),
        "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
        # "OPAL_POLICY_REPO_WEBHOOK_SECRET": "xxxxx",
        # "OPAL_POLICY_REPO_WEBHOOK_PARAMS": json.dumps(
        #     {
        #         "secret_header_name": "x-webhook-token",
        #         "secret_type": "token",
        #         "secret_parsing_regex": "(.*)",
        #         "event_request_key": "gitEvent",
        #         "push_event_value": "git.push",
        #     }
        # ),
        # "OPAL_AUTH_PUBLIC_KEY": os.getenv("OPAL_AUTH_PUBLIC_KEY", ""),
        # "OPAL_AUTH_PRIVATE_KEY": os.getenv("OPAL_AUTH_PRIVATE_KEY", ""),
        # "OPAL_AUTH_MASTER_TOKEN": os.getenv("OPAL_AUTH_MASTER_TOKEN", ""),
        # "OPAL_AUTH_JWT_AUDIENCE": "https://api.opal.ac/v1/",
        # "OPAL_AUTH_JWT_ISSUER": "https://opal.ac/",
        # "OPAL_STATISTICS_ENABLED": "true",
    }
    container = DockerContainer("permitio/opal-server")
    for envvar in environment.items():
        container = container.with_env(*envvar)
    container.start()
    print("port:", container.get_exposed_port(7002))
    wait_for_logs(container, "Clone succeeded")
    yield
    container.stop()


@pytest.fixture
def opal_client(): ...
