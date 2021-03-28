import os

from functools import partial
from typing import Optional
from pathlib import Path
from tenacity import retry, wait_fixed, stop_after_attempt, RetryError
from git import Repo, GitError, GitCommandError

from opal.common.logger import logger
from opal.common.git.exceptions import GitFailed
from opal.common.config import GIT_SSH_KEY_FILE


SSH_PREFIX = "ssh://"
GIT_SSH_USER_PREFIX = "git@"

def is_ssh_repo_url(repo_url: str):
    """
    return True if the repo url uses SSH authentication.
    (see: https://docs.github.com/en/github/authenticating-to-github/connecting-to-github-with-ssh)
    """
    return repo_url.startswith(SSH_PREFIX) or repo_url.startswith(GIT_SSH_USER_PREFIX)


class CloneResult:
    """
    wraps a git.Repo instance but knows if the repo was initialized with a url
    and cloned from a remote repo, or was initialed from a local `.git` repo.
    """
    def __init__(self, repo: Repo, cloned_from_remote: bool):
        self._repo = repo
        self._cloned_from_remote = cloned_from_remote

    @property
    def repo(self) -> Repo:
        """
        the wrapped repo instance
        """
        return self._repo

    @property
    def cloned_from_remote(self) -> bool:
        """
        whether the repo was cloned from remote, or we found a local matching .git repo
        """
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
    not already exists locally, and otherwise initialize the repo instance from
    the repo already existing on the filesystem.
    """

    DEFAULT_RETRY_CONFIG = {
        'wait': wait_fixed(5),
        'stop': stop_after_attempt(2),
        'reraise': True,
    }

    def __init__(
        self,
        repo_url: str,
        clone_path: str,
        retry_config = None,
        ssh_key: Optional[str] = None,
        ssh_key_file_path: Optional[str] = GIT_SSH_KEY_FILE,
    ):
        """inits the repo cloner.

        Args:
            repo_url (str): the url to the remote repo we want to clone
            clone_path (str): the target local path in our file system we want the
                repo to be cloned to
            retry_config (dict): Tenacity.retry config (@see https://tenacity.readthedocs.io/en/latest/api.html#retry-main-api)
            ssh_key (str, optional): private ssh key used to gain access to the cloned repo
            ssh_key_file_path (str, optional): local path to save the private ssh key contents
        """
        if repo_url is None:
            raise ValueError("must provide repo url!")

        self.url = repo_url
        self.path = os.path.expanduser(clone_path)
        self._ssh_key = ssh_key
        self._ssh_key_file_path = ssh_key_file_path
        self._retry_config = retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG

    def clone(self) -> CloneResult:
        """
        initializes a git.Repo and returns the clone result.
        it either:
            - does not found a cloned repo locally and clones from remote url
            - finds a cloned repo locally and does not clone from remote.
        """
        logger.info("Cloning repo from '{url}' to '{to_path}'", url=self.url, to_path=self.path)
        git_path = Path(self.path) / Path(".git")
        if git_path.exists():
            return self._attempt_init_from_local_repo()
        else:
            return self._attempt_clone_from_url()

    def _attempt_init_from_local_repo(self) -> CloneResult:
        """
        inits the repo from local .git or throws GitFailed
        """
        logger.info("Repo already exists in '{repo_path}'", repo_path=self.path)
        try:
            repo = Repo(self.path)
        except Exception as e:
            logger.exception("cannot init local repo: {error}", error=e)
            raise GitFailed(e)

        return LocalClone(repo)

    def _attempt_clone_from_url(self) -> CloneResult:
        """
        clones the repo from url or throws GitFailed
        """
        env = self._provide_git_ssh_environment()
        _clone_func = partial(Repo.clone_from, url=self.url, to_path=self.path, env=env)
        _clone_with_retries = retry(**self._retry_config)(_clone_func)
        try:
            repo = _clone_with_retries()
        except (GitError, GitCommandError) as e:
            logger.exception("cannot clone policy repo: {error}", error=e)
            raise GitFailed(e)
        except RetryError as e:
            logger.exception("cannot clone policy repo: {error}", error=e)
            raise GitFailed(e)
        else:
            logger.info("Clone succeeded", repo_path=self.path)
            return RemoteClone(repo)

    def _provide_git_ssh_environment(self):
        """
        provides git SSH configuration via GIT_SSH_COMMAND.

        the git ssh config will be provided only if the following conditions are met:
        - the repo url is a git ssh url
        - an ssh private key is provided in Repo Cloner __init__
        """
        if not is_ssh_repo_url(self.url) or self._ssh_key is None:
            return None # no ssh config
        git_ssh_identity_file = self._save_ssh_key_to_pem_file(self._ssh_key)
        return {
            "GIT_SSH_COMMAND": f"ssh -o StrictHostKeyChecking=no -i {git_ssh_identity_file}"
        }

    def _save_ssh_key_to_pem_file(self, key: str) -> Path:
        key = key.replace("_", "\n")
        if not key.endswith('\n'):
            key = key + '\n' # pem file must end with newline
        key_path = os.path.expanduser(self._ssh_key_file_path)
        parent_directory = os.path.dirname(key_path)
        if not os.path.exists(parent_directory):
            os.makedirs(parent_directory, exist_ok=True)
        with open(key_path, 'w') as f:
            f.write(key)
        os.chmod(key_path, 0o600)
        return Path(key_path)
