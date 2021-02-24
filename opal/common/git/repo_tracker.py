from typing import Tuple

from git import Repo, Head, Remote
from git.objects.commit import Commit
from tenacity import retry, wait_fixed, stop_after_attempt

from opal.common.logger import get_logger
from opal.common.config import POLICY_REPO_MAIN_BRANCH, POLICY_REPO_MAIN_REMOTE

logger = get_logger("Policy Watcher")

# retry in case of temp network error
GIT_PULL_RETRY_CONFIG = dict(wait=wait_fixed(3), stop=stop_after_attempt(2))

class GitFailed(Exception):
    """
    an exception we throw on git failures that are caused by wrong assumptions.
    i.e: we want to track a non-existing branch, or git url is not valid.
    """
    def __init__(self, exc: Exception):
        self._original_exc = exc
        super().__init__()


class RepoTracker:
    def __init__(
        self,
        repo: Repo,
        branch_name: str = POLICY_REPO_MAIN_BRANCH,
        remote_name: str = POLICY_REPO_MAIN_REMOTE,
    ):
        self._repo = repo
        self._branch_name = branch_name
        self._remote_name = remote_name
        self._save_latest_commit_as_prev_commit()

    @property
    def repo(self) -> Repo:
        return self._repo

    def pull(self) -> Tuple[bool, Commit, Commit]:
        """
        git pulls from tracked remote.
        returns a tuple of (has_changes, prev, latest)

        has_changes - whether the remote had new commits on our tracked branch
        prev - the previous (before the pull) top-most commit on the tracked branch
        latest - the new top-most (latest) commit on the tracked branch
        """
        self._pull()

        if (self.prev_commit.hexsha == self.latest_commit.hexsha):
            return False, self.prev_commit, self.prev_commit
        else:
            prev = self._prev_commit
            self._save_latest_commit_as_prev_commit()
            return True, prev, self.latest_commit

    @retry(**GIT_PULL_RETRY_CONFIG)
    def _pull(self):
        return self.tracked_remote.pull()

    def _save_latest_commit_as_prev_commit(self):
        self._prev_commit = self.latest_commit

    @property
    def tracked_branch(self) -> Head:
        try:
            return getattr(self._repo.heads, self._branch_name)
        except AttributeError as e:
            branches = [{'name': head.name, 'path': head.path} for head in self._repo.heads]
            logger.critical("did not find main branch", error=e, branches_found=branches)
            raise GitFailed(e)

    @property
    def latest_commit(self) -> Commit:
        return self.tracked_branch.commit

    @property
    def prev_commit(self) -> Commit:
        """
        latest commit before last git pull
        """
        return self._prev_commit

    @property
    def tracked_remote(self) -> Remote:
        try:
            return getattr(self._repo.remotes, self._remote_name)
        except AttributeError as e:
            branches = [{'name': head.name, 'path': head.path} for head in self._repo.heads]
            logger.critical("did not find main branch", error=e, branches_found=branches)
            raise GitFailed(e)
