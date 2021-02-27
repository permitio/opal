from functools import partial
from pathlib import Path
from tenacity import retry, wait_fixed, stop_after_attempt
from git import Repo, GitError, GitCommandError

from opal.common.logger import get_logger
from opal.common.git.repo_utils import GitFailed


class CloneResult:
    """
    wraps a git.Repo instance but knows if we cloned from remote or from local .git
    """
    def __init__(self, repo: Repo, cloned_from_remote: bool):
        self._repo = repo
        self._cloned_from_remote = cloned_from_remote

    @property
    def repo(self) -> Repo:
        return self._repo

    @property
    def cloned_from_remote(self) -> bool:
        return self._cloned_from_remote


class RemoteClone(CloneResult):
    def __init__(self, repo: Repo):
        super().__init__(repo=repo, cloned_from_remote=True)


class LocalClone(CloneResult):
    def __init__(self, repo: Repo):
        super().__init__(repo=repo, cloned_from_remote=False)


class RepoCloner:
    """
    simple wrapper for git.Repo() to simplify other classes that need to deal
    with the case where a repo must be cloned from url *only if* the repo does
    not already exists locally.
    """

    DEFAULT_RETRY_CONFIG = {
        'wait': wait_fixed(5),
        'stop': stop_after_attempt(2)
    }

    def __init__(
        self,
        repo_url: str,
        clone_path: str,
        retry_config = None,
    ):
        if repo_url is None:
            raise ValueError("must provide repo url!")

        self.url = repo_url
        self.path = clone_path
        self._retry_config = retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG

        self._logger = get_logger("opal.git.cloner")

    def clone(self) -> CloneResult:
        self._logger.info("Cloning repo", url=self.url, to_path=self.path)
        git_path = Path(self.path) / Path(".git")
        if git_path.exists():
            return self._attempt_init_from_local_repo()
        else:
            return self._attempt_clone_from_url()

    def _attempt_init_from_local_repo(self) -> CloneResult:
        """
        inits the repo from local .git or throws GitFailed
        """
        self._logger.info("Repo already exists", repo_path=self.path)
        try:
            repo = Repo(self.path)
        except Exception as e:
            self._logger.exception("cannot init local repo", error=e)
            raise GitFailed(e)

        return LocalClone(repo)

    def _attempt_clone_from_url(self) -> CloneResult:
        """
        clones the repo from url or throws GitFailed
        """
        _clone_func = partial(Repo.clone_from, url=self.url, to_path=self.path)
        _clone_with_retries = retry(**self._retry_config)(_clone_func)
        try:
            repo = _clone_with_retries()
        except (GitError, GitCommandError) as e:
            self._logger.exception("cannot clone policy repo", error=e)
            raise GitFailed(e)
        else:
            self._logger.info("Clone succeeded", repo_path=self.path)
            return RemoteClone(repo)
