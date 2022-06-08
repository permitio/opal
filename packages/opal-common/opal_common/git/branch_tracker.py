from functools import partial
from typing import Tuple

from git import GitCommandError, Head, Remote, Repo
from git.objects.commit import Commit
from opal_common.git.exceptions import GitFailed
from opal_common.logger import logger
from tenacity import retry, stop_after_attempt, wait_fixed


class BranchTracker:
    """tracks the state of a git branch (hash at branch HEAD).

    can also perform git pull and detect if the hash changed.
    """

    DEFAULT_RETRY_CONFIG = {
        "wait": wait_fixed(3),
        "stop": stop_after_attempt(2),
        "reraise": True,
    }

    def __init__(
        self,
        repo: Repo,
        branch_name: str = "master",
        remote_name: str = "origin",
        retry_config=None,
    ):
        """[summary]

        Args:
            repo (Repo): a git repo in which we want to track the latest commit of a branch
            branch_name (str): the branch we want to track
            remote_name (str): the remote in which the branch upstream is located
            retry_config (dict): Tenacity.retry config (@see https://tenacity.readthedocs.io/en/latest/api.html#retry-main-api)
        """
        self._repo = repo
        self._branch_name = branch_name
        self._remote_name = remote_name
        self._retry_config = (
            retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG
        )

        self.checkout()
        self._save_latest_commit_as_prev_commit()

    @property
    def repo(self) -> Repo:
        """the repo we are tracking."""
        return self._repo

    def pull(self) -> Tuple[bool, Commit, Commit]:
        """git pulls from tracked remote.

        Returns:
            pull_result (bool, Commit, Commit): a tuple consisting of:
                has_changes (bool): whether the remote had new commits on our tracked branch
                prev (Commit): the previous (before the pull) top-most commit on the tracked branch
                latest (Commit): the new top-most (latest) commit on the tracked branch
        """
        self._pull()

        if self.prev_commit.hexsha == self.latest_commit.hexsha:
            return False, self.prev_commit, self.prev_commit
        else:
            prev = self._prev_commit
            self._save_latest_commit_as_prev_commit()
            return True, prev, self.latest_commit

    def _pull(self):
        """runs git pull with retries."""
        attempt_pull = retry(**self._retry_config)(self.tracked_remote.pull)
        return attempt_pull()

    def checkout(self):
        """checkouts the desired branch."""
        checkout_func = partial(self._repo.git.checkout, self._branch_name)
        attempt_checkout = retry(**self._retry_config)(checkout_func)
        try:
            return attempt_checkout()
        except GitCommandError as e:
            branches = [
                {"name": head.name, "path": head.path} for head in self._repo.heads
            ]
            logger.error(
                "did not find main branch: {branch_name}, instead found: {branches_found}, got error: {error}",
                branch_name=self._branch_name,
                branches_found=branches,
                error=str(e),
            )
            raise GitFailed(e)

    def _save_latest_commit_as_prev_commit(self):
        """saves the top of the branch as a last known commit (HEAD).

        in the next pull, we can then compare the new branch HEAD to the
        previous _prev_commit.
        """
        self._prev_commit = self.latest_commit

    @property
    def latest_commit(self) -> Commit:
        """the top commit (HEAD) of the tracked branch."""
        return self.tracked_branch.commit

    @property
    def prev_commit(self) -> Commit:
        """the last previously known HEAD of the tracked branch."""
        return self._prev_commit

    @property
    def tracked_branch(self) -> Head:
        """returns the tracked branch object (of type git.HEAD) or throws if
        such branch does not exist on the repo."""
        try:
            return getattr(self._repo.heads, self._branch_name)
        except AttributeError as e:
            branches = [
                {"name": head.name, "path": head.path} for head in self._repo.heads
            ]
            logger.exception(
                "did not find main branch: {error}, instead found: {branches_found}",
                error=e,
                branches_found=branches,
            )
            raise GitFailed(e)

    @property
    def tracked_remote(self) -> Remote:
        """returns the tracked remote object (of type git.Remote) or throws if
        such remote does not exist on the repo."""
        try:
            return getattr(self._repo.remotes, self._remote_name)
        except AttributeError as e:
            remotes = [remote.name for remote in self._repo.remotes]
            logger.exception(
                "did not find main branch: {error}, instead found: {remotes_found}",
                error=e,
                remotes_found=remotes,
            )
            raise GitFailed(e)
