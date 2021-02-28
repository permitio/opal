from typing import Tuple

from git import Repo, Head, Remote
from git.objects.commit import Commit
from tenacity import retry, wait_fixed, stop_after_attempt

from opal.common.logger import get_logger
from opal.common.git.exceptions import GitFailed

logger = get_logger("Policy Watcher")


class BranchTracker:
    """
    tracks the state of a git branch (hash at branch HEAD).
    can also perform git pull and detect if the hash changed.
    """

    # retry config in case of temporary network error
    DEFAULT_RETRY_CONFIG = {
        'wait': wait_fixed(3),
        'stop': stop_after_attempt(2)
    }

    def __init__(
        self,
        repo: Repo,
        branch_name: str,
        remote_name: str,
        retry_config = None,
    ):
        self._repo = repo
        self._branch_name = branch_name
        self._remote_name = remote_name
        self._retry_config = retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG

        self._save_latest_commit_as_prev_commit()

    @property
    def repo(self) -> Repo:
        return self._repo

    def pull(self) -> Tuple[bool, Commit, Commit]:
        """
        git pulls from tracked remote.

        Returns:
            returns a tuple of (has_changes: bool, prev: Commit, latest: Commit)
                - has_changes: whether the remote had new commits on our tracked branch
                - prev: the previous (before the pull) top-most commit on the tracked branch
                - latest: the new top-most (latest) commit on the tracked branch
        """
        logger.info("Pulling changes from remote", remote=self.tracked_remote.name)
        self._pull()

        if (self.prev_commit.hexsha == self.latest_commit.hexsha):
            return False, self.prev_commit, self.prev_commit
        else:
            prev = self._prev_commit
            self._save_latest_commit_as_prev_commit()
            return True, prev, self.latest_commit

    def _pull(self):
        """
        runs git pull, retries if fails for some reason.
        """
        attempt_pull = retry(**self._retry_config)(self.tracked_remote.pull)
        return attempt_pull()

    def _save_latest_commit_as_prev_commit(self):
        self._prev_commit = self.latest_commit

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
    def tracked_branch(self) -> Head:
        try:
            return getattr(self._repo.heads, self._branch_name)
        except AttributeError as e:
            branches = [{'name': head.name, 'path': head.path} for head in self._repo.heads]
            logger.critical("did not find main branch", error=e, branches_found=branches)
            raise GitFailed(e)

    @property
    def tracked_remote(self) -> Remote:
        try:
            return getattr(self._repo.remotes, self._remote_name)
        except AttributeError as e:
            branches = [{'name': head.name, 'path': head.path} for head in self._repo.heads]
            logger.critical("did not find main branch", error=e, branches_found=branches)
            raise GitFailed(e)
