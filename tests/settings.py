import io
import json
import os
from contextlib import redirect_stdout
from secrets import token_hex
from typing import List

import pytest
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
            "OPAL_PYTEST_POLICY_REPO_PROVIDER", SupportedPolicyRepo.GITEA
        )
        self.repo_owner = os.getenv("OPAL_PYTEST_REPO_OWNER", "iwphonedo")
        self.repo_name = os.getenv("OPAL_PYTEST_REPO_NAME", "opal-example-policy-repo")
        self.repo_password = os.getenv("OPAL_PYTEST_REPO_PASSWORD")
        self.github_pat = os.getenv("OPAL_PYTEST_GITHUB_PAT")
        self.ssh_key_path = os.getenv("OPAL_PYTEST_SSH_KEY_PATH")
        self.source_repo_owner = os.getenv("OPAL_PYTEST_SOURCE_ACCOUNT", "permitio")
        self.source_repo_name = os.getenv(
            "OPAL_PYTEST_SOURCE_REPO", "opal-example-policy-repo"
        )
        self.webhook_secret = os.getenv("OPAL_PYTEST_WEBHOOK_SECRET", "xxxxx")
        self.should_fork = os.getenv("OPAL_PYTEST_SHOULD_FORK", "true")
        self.use_webhook = os.getenv("OPAL_PYTEST_USE_WEBHOOK", "true")

    def dump_settings(self):
        with open(f"pytest_{self.session_id}.env", "w") as envfile:
            envfile.write("#!/usr/bin/env bash\n\n")
            for key, val in globals().items():
                if key.startswith("OPAL") or key.startswith("UVICORN"):
                    envfile.write(f"export {key}='{val}'\n\n")


pytest_settings = TestSettings()
from testcontainers.core.utils import setup_logger


class PyTestSessionSettings(List):
    repo_providers = ["gitea", "github", "gitlab"]
    modes = ["with_webhook", "without_webhook"]
    broadcasters = ["postgres", "kafka", "redis"]
    broadcaster = "fgsfdg"
    repo_provider = "fdgdfg"
    mode = "rgrtre"

    def __init__(
        self,
        session_id: str = None,
        repo_provider: str = None,
        broadcaster: str = None,
        mode: str = None,
    ):
        super().__init__()

        self.session_id = session_id
        self.repo_provider = repo_provider
        self.broadcaster = broadcaster
        self.mode = mode

        self.current_broadcaster = 0
        self.current_repo_provider = 0
        self.current_mode = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.current_broadcaster >= len(self.broadcasters):
            raise StopIteration

        while self.current_broadcaster < len(self.broadcasters):
            # Update settings
            self.broadcaster = self.broadcasters[self.current_broadcaster]
            self.repo_provider = self.repo_providers[self.current_repo_provider]
            self.mode = self.modes[self.current_mode]
            # Move to the next combination
            self.current_mode += 1
            if self.current_mode >= len(self.modes):
                self.current_mode = 0
                self.current_repo_provider += 1
                if self.current_repo_provider >= len(self.repo_providers):
                    self.current_repo_provider = 0
                    self.current_broadcaster += 1

            return {
                "session_id": self.session_id,
                "repo_provider": self.repo_provider,
                "broadcaster": self.broadcaster,
                "mode": self.mode,
                "is_final": ((self.current_broadcaster >= len(self.broadcasters)) and (self.current_repo_provider >= len(self.repo_providers)) and (self.current_mode >= len(self.modes))),
            }

        print("Finished iterating over PyTestSessionSettings...")


@pytest.fixture(params=list(PyTestSessionSettings()), scope="session")
def session_matrix(request):
    return request.param

    # settings = PyTestSessionSettings()
    # for setting in settings:
    #     yield setting
