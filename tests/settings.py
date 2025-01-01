import io
import json
import os
from contextlib import redirect_stdout
from secrets import token_hex

from dotenv import load_dotenv
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
        load_dotenv()

        self.policy_repo_provider = os.getenv(
            "OPAL_PYTEST_POLICY_REPO_PROVIDER", SupportedPolicyRepo.GITHUB
        )
        self.repo_owner = os.getenv("OPAL_PYTEST_REPO_OWNER", "iwphonedo")
        self.repo_name = os.getenv("OPAL_PYTEST_REPO_NAME", "opal-example-policy-repo")
        self.repo_password = os.getenv("OPAL_PYTEST_REPO_PASSWORD")
        self.github_pat = os.getenv("OPAL_PYTEST_GITHUB_PAT", None)
        self.ssh_key_path = os.getenv("OPAL_PYTEST_SSH_KEY_PATH")
        self.source_repo_owner = os.getenv("OPAL_PYTEST_SOURCE_ACCOUNT", "permitio")
        self.source_repo_name = os.getenv(
            "OPAL_PYTEST_SOURCE_REPO", "opal-example-policy-repo"
        )
        self.webhook_secret = os.getenv("OPAL_PYTEST_WEBHOOK_SECRET", "xxxxx")
        self.should_fork = os.getenv("OPAL_PYTEST_SHOULD_FORK", "true")

    def dump_settings(self):
        with open(f"pytest_{self.session_id}.env", "w") as envfile:
            envfile.write("#!/usr/bin/env bash\n\n")
            for key, val in globals().items():
                if key.startswith("OPAL") or key.startswith("UVICORN"):
                    envfile.write(f"export {key}='{val}'\n\n")
