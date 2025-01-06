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
        """Initialize settings for the test session.

        This method creates a new session ID, then loads settings from environment
        variables. The session ID is a 2-character hexadecimal string, and is used to
        identify the test session for logging and debugging purposes.

        The settings loaded from environment variables are as follows:

        - OPAL_PYTEST_POLICY_REPO_PROVIDER: The policy repository provider to use
          for the test session. Valid values are 'GITEA' and 'GITHUB'. If not set,
          defaults to 'GITEA'.
        """
        self.session_id = token_hex(2)

        self.load_from_env()

    def load_from_env(self):
        """Loads environment variables into the test settings.

        This function loads the environment variables using the `load_dotenv` function
        and assigns them to various attributes of the settings object. The environment
        variables control various aspects of the test session, such as the policy
        repository provider, repository details, authentication credentials, and
        configuration options for the test environment.

        Attributes set by this function:
        - policy_repo_provider: The provider for the policy repository. Defaults to GITEA.
        - repo_owner: The owner of the policy repository. Defaults to "iwphonedo".
        - repo_name: The name of the policy repository. Defaults to "opal-example-policy-repo".
        - repo_password: The password for accessing the policy repository.
        - github_pat: The GitHub personal access token for accessing the repository.
        - ssh_key_path: The path to the SSH key used for repository access.
        - source_repo_owner: The owner of the source repository. Defaults to "permitio".
        - source_repo_name: The name of the source repository. Defaults to "opal-example-policy-repo".
        - webhook_secret: The secret used for authenticating webhooks. Defaults to "xxxxx".
        - should_fork: Whether to fork the repository. Defaults to "true".
        - use_webhook: Whether to use webhooks for triggering updates. Defaults to "true".
        - wait_for_debugger: Whether to wait for a debugger. Defaults to "false".
        - skip_rebuild_images: Whether to skip rebuilding Docker images. Defaults to "false".
        - keep_images: Whether to keep Docker images after tests. Defaults to "true".
        """

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
        self.wait_for_debugger = os.getenv("OPAL_PYTEST_WAIT_FOR_DEBUGGER", "false")

        self.skip_rebuild_images = os.getenv("OPAL_PYTEST_SKIP_REBUILD_IMAGES", "true")
        self.keep_images = os.getenv("OPAL_PYTEST_KEEP_IMAGES", "true")

    def dump_settings(self):
        with open(f"pytest_{self.session_id}.env", "w") as envfile:
            envfile.write("#!/usr/bin/env bash\n\n")
            for key, val in globals().items():
                if key.startswith("OPAL") or key.startswith("UVICORN"):
                    envfile.write(f"export {key}='{val}'\n\n")


pytest_settings = TestSettings()
from testcontainers.core.utils import setup_logger


class PyTestSessionSettings(List):
    repo_providers = ["gitea"]
    modes = ["without_webhook"]
    broadcasters = ["postgres"]
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
                "is_final": (
                    (self.current_broadcaster >= len(self.broadcasters))
                    and (self.current_repo_provider >= len(self.repo_providers))
                    and (self.current_mode >= len(self.modes))
                ),
                "is_first": (
                    (self.current_broadcaster <= 0)
                    and (self.current_repo_provider <= 0)
                    and (self.current_mode <= 0)
                ),
            }

        print("Finished iterating over PyTestSessionSettings...")


@pytest.fixture(params=list(PyTestSessionSettings()), scope="session")
def session_matrix(request):
    print
    return request.param
