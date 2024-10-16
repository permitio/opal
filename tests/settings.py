import json
from secrets import token_hex
from os import getenv as _

from testcontainers.core.generic import DockerContainer

UVICORN_NUM_WORKERS = _("UVICORN_NUM_WORKERS", "4")
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
OPAL_AUTH_PUBLIC_KEY = _("OPAL_AUTH_PUBLIC_KEY", "")
OPAL_AUTH_PRIVATE_KEY = _("OPAL_AUTH_PRIVATE_KEY", "")
OPAL_AUTH_MASTER_TOKEN = _("OPAL_AUTH_MASTER_TOKEN", token_hex(16))
OPAL_AUTH_JWT_AUDIENCE = _("OPAL_AUTH_JWT_AUDIENCE", "https://api.opal.ac/v1/")
OPAL_AUTH_JWT_ISSUER = _("OPAL_AUTH_JWT_ISSUER", "https://opal.ac/")
OPAL_STATISTICS_ENABLED = _("OPAL_STATISTICS_ENABLED", "true")

_opal_server_tmp_container = (
    DockerContainer("permitio/opal-server")
    .with_env("OPAL_REPO_WATCHER_ENABLED", "0")
    .with_env("OPAL_AUTH_MASTER_TOKEN", OPAL_AUTH_MASTER_TOKEN)
    .with_env("OPAL_AUTH_JWT_AUDIENCE", OPAL_AUTH_JWT_AUDIENCE)
    .with_env("OPAL_AUTH_JWT_ISSUER", OPAL_AUTH_JWT_ISSUER)
)

OPAL_DATA_CONFIG_SOURCES = {
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
