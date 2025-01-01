import os
from enum import Enum

from tests.policy_repos.gitea_policy_repo import GiteaPolicyRepo
from tests.policy_repos.github_policy_repo import GithubPolicyRepo
from tests.policy_repos.gitlab_policy_repo import GitlabPolicyRepo
from tests.policy_repos.policy_repo_base import PolicyRepoBase


class SupportedPolicyRepo(Enum):
    GITEA = "Gitea"
    GITHUB = "Github"
    GITLAB = "Gitlab"


class PolicyRepoFactory:
    def __init__(self, policy_repo: str = SupportedPolicyRepo.GITEA):
        self.assert_exists(policy_repo)

        self.policy_repo = policy_repo

    def get_policy_repo(self,
        temp_dir: str,
        owner: str | None = None,
        repo: str | None = None,
        password: str | None = None,
        github_pat: str | None = None,
        ssh_key_path: str | None = None,
        source_repo_owner: str | None = None,
        source_repo_name: str | None = None,
        should_fork: bool = False,
        webhook_secret: str | None = None,) -> PolicyRepoBase:
        
        factory = {
            SupportedPolicyRepo.GITEA: GiteaPolicyRepo,
            SupportedPolicyRepo.GITHUB: GithubPolicyRepo,
            SupportedPolicyRepo.GITLAB: GitlabPolicyRepo,
        }

        return factory[SupportedPolicyRepo(self.policy_repo)](temp_dir, owner, repo, password, github_pat, ssh_key_path, source_repo_owner, source_repo_name, should_fork, webhook_secret)

    def assert_exists(self, policy_repo: str) -> bool:
        try:
            source_enum = SupportedPolicyRepo(policy_repo)
        except ValueError:
            raise ValueError(
                f"Unsupported REPO_SOURCE value: {policy_repo}. Must be one of {[e.value for e in SupportedPolicyRepo]}"
            )
