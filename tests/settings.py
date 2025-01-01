import io
import json
import os
from contextlib import redirect_stdout
from secrets import token_hex

from opal_common.cli.commands import obtain_token
from opal_common.schemas.security import PeerType
from testcontainers.core.generic import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from tests.policy_repos.policy_repo_factory import SupportedPolicyRepo


class TestSettings:
    def __init__(self):
        self.session_id = token_hex(2)

        self.load_from_env()

    def load_from_env(self):
        self.policy_repo_provider = os.getenv(
            "OPAL_PYTEST_POLICY_REPO_PROVIDER", SupportedPolicyRepo.GITHUB
        )

    # OPAL_TESTS_DEBUG = _("OPAL_TESTS_DEBUG") is not None
    # print(f"OPAL_TESTS_DEBUG={OPAL_TESTS_DEBUG}")

    # OPAL_TESTS_UNIQ_ID = token_hex(2)
    # print(f"OPAL_TESTS_UNIQ_ID={OPAL_TESTS_UNIQ_ID}")

    # OPAL_TESTS_NETWORK_NAME = f"pytest_opal_{OPAL_TESTS_UNIQ_ID}"
    # OPAL_TESTS_SERVER_CONTAINER_NAME = f"pytest_opal_server_{OPAL_TESTS_UNIQ_ID}"
    # OPAL_TESTS_CLIENT_CONTAINER_NAME = f"pytest_opal_client_{OPAL_TESTS_UNIQ_ID}"

    # OPAL_AUTH_PUBLIC_KEY = _("OPAL_AUTH_PUBLIC_KEY", "")
    # OPAL_AUTH_PRIVATE_KEY = _("OPAL_AUTH_PRIVATE_KEY", "")
    # OPAL_AUTH_PRIVATE_KEY_PASSPHRASE = _("OPAL_AUTH_PRIVATE_KEY_PASSPHRASE")
    # OPAL_AUTH_MASTER_TOKEN = _("OPAL_AUTH_MASTER_TOKEN", token_hex(16))
    # OPAL_AUTH_JWT_AUDIENCE = _("OPAL_AUTH_JWT_AUDIENCE", "https://api.opal.ac/v1/")
    # OPAL_AUTH_JWT_ISSUER = _("OPAL_AUTH_JWT_ISSUER", "https://opal.ac/")

    # OPAL_IMAGE_TAG = _("OPAL_IMAGE_TAG", "latest")
    # # Temporary container to generate the required tokens.
    # _container = (
    #     DockerContainer(f"permitio/opal-server:{OPAL_IMAGE_TAG}")
    #     .with_exposed_ports(7002)
    #     .with_env("OPAL_REPO_WATCHER_ENABLED", "0")
    #     .with_env("OPAL_AUTH_PUBLIC_KEY", OPAL_AUTH_PUBLIC_KEY)
    #     .with_env("OPAL_AUTH_PRIVATE_KEY", OPAL_AUTH_PRIVATE_KEY)
    #     .with_env("OPAL_AUTH_MASTER_TOKEN", OPAL_AUTH_MASTER_TOKEN)
    #     .with_env("OPAL_AUTH_JWT_AUDIENCE", OPAL_AUTH_JWT_AUDIENCE)
    #     .with_env("OPAL_AUTH_JWT_ISSUER", OPAL_AUTH_JWT_ISSUER)
    # )

    # OPAL_CLIENT_TOKEN = _("OPAL_CLIENT_TOKEN")
    # # OPAL_DATA_SOURCE_TOKEN = _("OPAL_DATA_SOURCE_TOKEN")

    # with _container:
    #     wait_for_logs(_container, "OPAL Server Startup")
    #     kwargs = {
    #         "master_token": OPAL_AUTH_MASTER_TOKEN,
    #         "server_url": f"http://{_container.get_container_host_ip()}:{_container.get_exposed_port(7002)}",
    #         "ttl": (365, "days"),
    #         "claims": {},
    #     }

    #     if not OPAL_CLIENT_TOKEN:
    #         with io.StringIO() as stdout:
    #             with redirect_stdout(stdout):
    #                 obtain_token(type=PeerType("client"), **kwargs)
    #             OPAL_CLIENT_TOKEN = stdout.getvalue().strip()

    #     if not OPAL_DATA_SOURCE_TOKEN:
    #         with io.StringIO() as stdout:
    #             with redirect_stdout(stdout):
    #                 obtain_token(type=PeerType("datasource"), **kwargs)
    #             OPAL_DATA_SOURCE_TOKEN = stdout.getvalue().strip()

    # UVICORN_NUM_WORKERS = _("UVICORN_NUM_WORKERS", "4")
    # OPAL_STATISTICS_ENABLED = _("OPAL_STATISTICS_ENABLED", "true")

    # OPAL_POLICY_REPO_URL = os.getenv(
    #     "OPAL_POLICY_REPO_URL", "git@github.com:permitio/opal-tests-policy-repo.git"
    # )
    # OPAL_POLICY_REPO_MAIN_BRANCH = os.getenv("OPAL_POLICY_REPO_MAIN_BRANCH", "main")

    # OPAL_POLICY_REPO_SSH_KEY = _("OPAL_POLICY_REPO_SSH_KEY", "")
    # OPAL_POLICY_REPO_POLLING_INTERVAL = _("OPAL_POLICY_REPO_POLLING_INTERVAL", "30")
    # OPAL_LOG_FORMAT_INCLUDE_PID = _("OPAL_LOG_FORMAT_INCLUDE_PID ", "true")
    # OPAL_POLICY_REPO_WEBHOOK_SECRET = _("OPAL_POLICY_REPO_WEBHOOK_SECRET", "xxxxx")
    # OPAL_POLICY_REPO_WEBHOOK_PARAMS = _(
    # "OPAL_POLICY_REPO_WEBHOOK_PARAMS",
    # json.dumps(
    #     {
    #         "secret_header_name": "x-webhook-token",
    #         "secret_type": "token",
    #         "secret_parsing_regex": "(.*)",
    #         "event_request_key": "gitEvent",
    #         "push_event_value": "git.push",
    #     }
    # ),
    # )

    # _url = f"http://{OPAL_TESTS_SERVER_CONTAINER_NAME}.{OPAL_TESTS_NETWORK_NAME}:7002/policy-data"
    # OPAL_DATA_CONFIG_SOURCES = json.dumps(
    #     {
    #         "config": {
    #             "entries": [
    #                 {
    #                     "url": _url,
    #                     "config": {
    #                         "headers": {"Authorization": f"Bearer {OPAL_CLIENT_TOKEN}"}
    #                     },
    #                     "topics": ["policy_data"],
    #                     "dst_path": "/static",
    #                 }
    #             ]
    #         }
    #     }
    # )

    # # Opal Client
    # OPAL_INLINE_OPA_LOG_FORMAT = "http"
    # OPAL_SHOULD_REPORT_ON_DATA_UPDATES = "true"
    # OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED = "true"
    # OPAL_DEFAULT_UPDATE_CALLBACKS = json.dumps(
    #     {
    #         "callbacks": [
    #             [
    #                 f"http://{OPAL_TESTS_SERVER_CONTAINER_NAME}.{OPAL_TESTS_NETWORK_NAME}:7002/data/callback_report",
    #                 {
    #                     "method": "post",
    #                     "process_data": False,
    #                     "headers": {
    #                         "Authorization": f"Bearer {OPAL_CLIENT_TOKEN}",
    #                         "content-type": "application/json",
    #                     },
    #                 },
    #             ]
    #         ]
    #     }
    # )

    def dump_settings(self):
        with open(f"pytest_{self.session_id}.env", "w") as envfile:
            envfile.write("#!/usr/bin/env bash\n\n")
            for key, val in globals().items():
                if key.startswith("OPAL") or key.startswith("UVICORN"):
                    envfile.write(f"export {key}='{val}'\n\n")
