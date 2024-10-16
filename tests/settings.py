import io
from contextlib import redirect_stdout
import json
from os import getenv as _
from secrets import token_hex

from opal_common.cli.commands import obtain_token
from opal_common.schemas.security import PeerType
from testcontainers.core.generic import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs


OPAL_AUTH_PUBLIC_KEY = _("OPAL_AUTH_PUBLIC_KEY", "")
OPAL_AUTH_PRIVATE_KEY = _("OPAL_AUTH_PRIVATE_KEY", "")
OPAL_AUTH_MASTER_TOKEN = _("OPAL_AUTH_MASTER_TOKEN", token_hex(16))
OPAL_AUTH_JWT_AUDIENCE = _("OPAL_AUTH_JWT_AUDIENCE", "https://api.opal.ac/v1/")
OPAL_AUTH_JWT_ISSUER = _("OPAL_AUTH_JWT_ISSUER", "https://opal.ac/")

# Temporary container to generate the required tokens.
_container = (
    DockerContainer("permitio/opal-server")
    .with_bind_ports(7002)
    .with_env("OPAL_REPO_WATCHER_ENABLED", "0")
    .with_env("OPAL_AUTH_PUBLIC_KEY", OPAL_AUTH_PUBLIC_KEY)
    .with_env("OPAL_AUTH_PRIVATE_KEY", OPAL_AUTH_PRIVATE_KEY)
    .with_env("OPAL_AUTH_MASTER_TOKEN", OPAL_AUTH_MASTER_TOKEN)
    .with_env("OPAL_AUTH_JWT_AUDIENCE", OPAL_AUTH_JWT_AUDIENCE)
    .with_env("OPAL_AUTH_JWT_ISSUER", OPAL_AUTH_JWT_ISSUER)
)

with _container, io.StringIO() as stdout:
    wait_for_logs(_container, "OPAL Server Startup")
    kwargs = {
        "master_token": OPAL_AUTH_MASTER_TOKEN,
        "server_url": f"http://{_container.get_container_host_ip()}:{_container.get_exposed_port(7002)}",
        "ttl": (365, "days"),
        "claims": {},
    }

    with redirect_stdout(stdout):
        obtain_token(type=PeerType("client"), **kwargs)
    OPAL_CLIENT_TOKEN = stdout.getvalue().strip()

    stdout.seek(0)  # Overwrite the buffer.

    with redirect_stdout(stdout):
        obtain_token(type=PeerType("datasource"), **kwargs)
    OPAL_DATA_SOURCE_TOKEN = stdout.getvalue().strip()

UVICORN_NUM_WORKERS = _("UVICORN_NUM_WORKERS", "4")
OPAL_STATISTICS_ENABLED = _("OPAL_STATISTICS_ENABLED", "true")
OPAL_POLICY_REPO_URL = _(
    "OPAL_POLICY_REPO_URL", "git@github.com:permitio/opal-tests-policy-repo.git"
)
OPAL_POLICY_REPO_SSH_KEY = _("OPAL_POLICY_REPO_SSH_KEY", "")
OPAL_POLICY_REPO_MAIN_BRANCH = _("POLICY_REPO_BRANCH", "main")
OPAL_POLICY_REPO_POLLING_INTERVAL = _("OPAL_POLICY_REPO_POLLING_INTERVAL", "30")
OPAL_LOG_FORMAT_INCLUDE_PID = _("OPAL_LOG_FORMAT_INCLUDE_PID ", "true")
OPAL_POLICY_REPO_WEBHOOK_SECRET = _("OPAL_POLICY_REPO_WEBHOOK_SECRET", "xxxxx")
OPAL_POLICY_REPO_WEBHOOK_PARAMS = _(
    "OPAL_POLICY_REPO_WEBHOOK_PARAMS",
    json.dumps(
        {
            "secret_header_name": "x-webhook-token",
            "secret_type": "token",
            "secret_parsing_regex": "(.*)",
            "event_request_key": "gitEvent",
            "push_event_value": "git.push",
        }
    ),
)

OPAL_DATA_CONFIG_SOURCES = json.dumps(
    {
        "config": {
            "entries": [
                {
                    # TODO: Replace this
                    "url": "http://localhost:7002/policy-data",
                    "config": {
                        "headers": {"Authorization": f"Bearer {OPAL_CLIENT_TOKEN}"}
                    },
                    "topics": ["policy_data"],
                    "dst_path": "/static",
                }
            ]
        }
    }
)

# Opal Client
OPAL_INLINE_OPA_LOG_FORMAT = "http"
OPAL_SHOULD_REPORT_ON_DATA_UPDATES = True
OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED = True
OPAL_DEFAULT_UPDATE_CALLBACKS = json.dumps(
    {
        "callbacks": [
            [
                "http://localhost:7002/data/callback_report",
                {
                    "method": "post",
                    "process_data": False,
                    "headers": {
                        "Authorization": f"Bearer {OPAL_CLIENT_TOKEN}",
                        "content-type": "application/json",
                    },
                },
            ]
        ]
    }
)
