from pathlib import Path

from opal_common.schemas.policy_source import (
    BasePolicyScopeSource,
    GitPolicyScopeSource,
)
from pygit2 import Repository


def is_same_scope(source: BasePolicyScopeSource, directory: Path) -> bool:
    if isinstance(source, GitPolicyScopeSource) and (directory / ".git").exists():
        repo = Repository(directory)

        if (
            repo.remotes["origin"].url == source.url
            and repo.head.name
            and source.branch
        ):
            return True

    return False
