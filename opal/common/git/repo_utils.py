from typing import List

from pathlib import Path
from git import Repo, DiffIndex
from git.objects.commit import Commit


class GitActions:
    @classmethod
    def repo_dir(cls, repo: Repo) -> Path:
        return Path(repo.git_dir).parent

    @classmethod
    def diff_between_commits(cls, old: Commit, new: Commit) -> DiffIndex:
        return old.diff(new)

    @classmethod
    def files_affected_in_diff(cls, diff_list: DiffIndex) -> List[Path]:
        return []
