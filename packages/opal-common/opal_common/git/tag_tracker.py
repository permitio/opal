from functools import partial
from typing import Optional, Tuple

from git import GitCommandError, Reference, Repo, Tag
from git.objects.commit import Commit
from opal_common.git.branch_tracker import BranchTracker
from opal_common.git.env import provide_git_ssh_environment
from opal_common.git.exceptions import GitFailed
from opal_common.logger import logger
from tenacity import retry, stop_after_attempt, wait_fixed


class TagTracker(BranchTracker):
    """Tracks the state of a git tag (hash the tag is pointing at).

    Can detect if the tag has been moved to point at a different commit.
    """

    def __init__(
        self,
        repo: Repo,
        tag_name: str,
        remote_name: str = "origin",
        retry_config=None,
        ssh_key: Optional[str] = None,
    ):
        """Initializes the TagTracker.

        Args:
            repo (Repo): a git repo in which we want to track the specific commit a tag is pointing to
            tag_name (str): the tag we want to track
            remote_name (str): the remote in which the tag is located
            retry_config (dict): Tenacity.retry config
            ssh_key (Optional[str]): SSH key for private repositories
        """
        self._tag_name = tag_name
        super().__init__(
            repo,
            branch_name=None,
            remote_name=remote_name,
            retry_config=retry_config,
            ssh_key=ssh_key,
        )

    def checkout(self):
        """Checkouts the repository at the current tag."""
        checkout_func = partial(self._repo.git.checkout, self._tag_name)
        attempt_checkout = retry(**self._retry_config)(checkout_func)
        try:
            return attempt_checkout()
        except GitCommandError as e:
            tags = [tag.name for tag in self._repo.tags]
            logger.error(
                "did not find tag: {tag_name}, instead found: {tags_found}, got error: {error}",
                tag_name=self._tag_name,
                tags_found=tags,
                error=str(e),
            )
            raise GitFailed(e)

    def _fetch(self):
        """Fetch updates including tags with force option."""

        def _inner_fetch(*args, **kwargs):
            env = provide_git_ssh_environment(self.tracked_remote.url, self._ssh_key)
            with self.tracked_remote.repo.git.custom_environment(**env):
                self.tracked_remote.repo.git.fetch("--tags", "--force", *args, **kwargs)

        attempt_fetch = retry(**self._retry_config)(_inner_fetch)
        return attempt_fetch()

    @property
    def latest_commit(self) -> Commit:
        """the commit of the tracked tag."""
        return self.tracked_tag.commit

    @property
    def tracked_tag(self) -> Tag:
        """returns the tracked tag reference (of type git.Reference) or throws
        if such tag does not exist on the repo."""
        try:
            return getattr(self._repo.tags, self._tag_name)
        except AttributeError as e:
            tags = [{"path": tag.path} for tag in self._repo.tags]
            logger.exception(
                "did not find main branch: {error}, instead found: {tags_found}",
                error=e,
                tags_found=tags,
            )
            raise GitFailed(e)

    @property
    def tracked_reference(self) -> Reference:
        return self.tracked_tag

    def pull(self) -> Tuple[bool, Commit, Commit]:
        """Overrides the pull method to handle tag updates.

        Returns:
            pull_result (bool, Commit, Commit): a tuple consisting of:
                has_changes (bool): whether the tag has been moved to a different commit
                prev (Commit): the previous commit the tag was pointing to
                latest (Commit): the new commit the tag is currently pointing to
        """
        self._fetch()
        self.checkout()

        if self.prev_commit.hexsha == self.latest_commit.hexsha:
            return False, self.prev_commit, self.prev_commit
        else:
            prev = self._prev_commit
            self._save_latest_commit_as_prev_commit()
            return True, prev, self.latest_commit
