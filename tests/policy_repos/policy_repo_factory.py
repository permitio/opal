import logging
import os
from enum import Enum

from testcontainers.core.utils import setup_logger

from tests.policy_repos.gitea_policy_repo import GiteaPolicyRepo
from tests.policy_repos.github_policy_repo import GithubPolicyRepo
from tests.policy_repos.gitlab_policy_repo import GitlabPolicyRepo
from tests.policy_repos.policy_repo_base import PolicyRepoBase
from tests.policy_repos.policy_repo_settings import PolicyRepoSettings


class SupportedPolicyRepo(Enum):
    GITEA = "Gitea"
    GITHUB = "Github"
    GITLAB = "Gitlab"
    # BITBUCKET = "Bitbucket"
    # AZURE_DEVOPS = "AzureDevOps"


# Factory class to create a policy repository object based on the type of policy repository.
class PolicyRepoFactory:
    def __init__(self, policy_repo: str = SupportedPolicyRepo.GITEA):
        """
        :param policy_repo: The type of policy repository. Defaults to GITEA.
        """
        self.assert_exists(policy_repo)

        self.policy_repo = policy_repo

    def get_policy_repo(
        self,
        settings: PolicyRepoSettings,
        logger: logging.Logger = setup_logger(__name__),
    ) -> PolicyRepoBase:
        factory = {
            SupportedPolicyRepo.GITEA: GiteaPolicyRepo,
            SupportedPolicyRepo.GITHUB: GithubPolicyRepo,
            SupportedPolicyRepo.GITLAB: GitlabPolicyRepo,
        }

        return factory[SupportedPolicyRepo(self.policy_repo)](settings)

    def assert_exists(self, policy_repo: str) -> bool:
        try:
            source_enum = SupportedPolicyRepo(policy_repo)
        except ValueError:
            raise ValueError(
                f"Unsupported REPO_SOURCE value: {policy_repo}. Must be one of {[e.value for e in SupportedPolicyRepo]}"
            )
