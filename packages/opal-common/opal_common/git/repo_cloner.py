import asyncio
import os
import shutil
import uuid
from functools import partial
from pathlib import Path
from typing import Generator, Optional

from git import GitCommandError, GitError, Repo
from opal_common.config import opal_common_config
from opal_common.git.exceptions import GitFailed
from opal_common.logger import logger
from opal_common.utils import get_filepaths_with_glob
from tenacity import RetryError, retry, stop, wait

SSH_PREFIX = "ssh://"
GIT_SSH_USER_PREFIX = "git@"


def is_ssh_repo_url(repo_url: str):
    """return True if the repo url uses SSH authentication.

    (see: https://docs.github.com/en/github/authenticating-to-github/connecting-to-github-with-ssh)
    """
    return repo_url.startswith(SSH_PREFIX) or repo_url.startswith(GIT_SSH_USER_PREFIX)


class CloneResult:
    """wraps a git.Repo instance but knows if the repo was initialized with a
    url and cloned from a remote repo, or was initialed from a local `.git`
    repo."""

    def __init__(self, repo: Repo):
        self._repo = repo

    @property
    def repo(self) -> Repo:
        """the wrapped repo instance."""
        return self._repo


class RepoClonePathFinder:
    """
    We are cloning the policy repo into a unique random subdirectory of a base path.
    Args:
        base_clone_path (str): parent directory for the repoistory clone
        clone_subdirectory_prefix (str): the prefix for the randomized repository dir, or the dir name itself when `use_fixes_path=true`
        use_fixed_path (bool): if set, random suffix won't be added to `clone_subdirectory_prefix` (if the path already exists, it would be reused)

    This class knows how to such clones, so we can discard previous ones, but also so
    that siblings workers (who are not the master who decided where to clone) can also
    find the current clone by globing the base dir.
    """

    def __init__(
        self, base_clone_path: str, clone_subdirectory_prefix: str, use_fixed_path: bool
    ):
        if not base_clone_path:
            raise ValueError("base_clone_path cannot be empty!")

        if not clone_subdirectory_prefix:
            raise ValueError("clone_subdirectory_prefix cannot be empty!")

        self._base_clone_path = os.path.expanduser(base_clone_path)
        self._clone_subdirectory_prefix = clone_subdirectory_prefix
        self._use_fixed_path = use_fixed_path

    def _get_randomized_clone_subdirectories(self) -> Generator[str, None, None]:
        """a generator yielding all the randomized subdirectories of the base
        clone path that are matching the clone pattern.

        Yields:
            the next subdirectory matching the pattern
        """
        folders_with_pattern = get_filepaths_with_glob(
            self._base_clone_path, f"{self._clone_subdirectory_prefix}-*"
        )
        for folder in folders_with_pattern:
            yield folder

    def _get_single_existing_random_clone_path(self) -> Optional[str]:
        """searches for the single randomly-suffixed clone subdirectory in
        existance.

        If found no such subdirectory or if found more than one (multiple matching subdirectories) - will return None.
        otherwise: will return the single and only clone.
        """
        subdirectories = list(self._get_randomized_clone_subdirectories())
        if len(subdirectories) != 1:
            return None
        return subdirectories[0]

    def _generate_randomized_clone_path(self) -> str:
        folder_name = f"{self._clone_subdirectory_prefix}-{uuid.uuid4().hex}"
        full_local_repo_path = os.path.join(self._base_clone_path, folder_name)
        return full_local_repo_path

    def _get_fixed_clone_path(self) -> str:
        return os.path.join(self._base_clone_path, self._clone_subdirectory_prefix)

    def get_clone_path(self) -> Optional[str]:
        """Get the clone path (fixed or randomized) if it exists."""
        if self._use_fixed_path:
            fixed_path = self._get_fixed_clone_path()
            if os.path.exists(fixed_path):
                return fixed_path
            else:
                return None
        else:
            return self._get_single_existing_random_clone_path()

    def create_new_clone_path(self) -> str:
        """
        If using a fixed path - simply creates it.
        If using a randomized suffix -
            takes the base path from server config and create new folder with unique name for the local clone.
            The folder name is looks like /<base-path>/<folder-prefix>-<uuid>
            If such folders already exist they would be removed.
        """
        if self._use_fixed_path:
            # When using fixed path - just use old path without cleanup
            full_local_repo_path = self._get_fixed_clone_path()
        else:
            # Remove old randomized subdirectories
            for folder in self._get_randomized_clone_subdirectories():
                logger.warning(
                    "Found previous policy repo clone: {folder_name}, removing it to avoid conflicts.",
                    folder_name=folder,
                )
                shutil.rmtree(folder)
            full_local_repo_path = self._generate_randomized_clone_path()

        os.makedirs(full_local_repo_path, exist_ok=True)
        return full_local_repo_path


class RepoCloner:
    """simple wrapper for git.Repo() to simplify other classes that need to
    deal with the case where a repo must be cloned from url *only if* the repo
    does not already exists locally, and otherwise initialize the repo instance
    from the repo already existing on the filesystem."""

    # wait indefinitely until successful
    DEFAULT_RETRY_CONFIG = {
        "wait": wait.wait_random_exponential(multiplier=0.5, max=30),
    }

    def __init__(
        self,
        repo_url: str,
        clone_path: str,
        branch_name: str = "master",
        retry_config=None,
        ssh_key: Optional[str] = None,
        ssh_key_file_path: Optional[str] = None,
        clone_timeout: int = 0,
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
        self.branch_name = branch_name
        self._ssh_key = ssh_key
        self._ssh_key_file_path = (
            ssh_key_file_path or opal_common_config.GIT_SSH_KEY_FILE
        )
        self._retry_config = (
            retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG
        )
        if clone_timeout > 0:
            self._retry_config.update({"stop": stop.stop_after_delay(clone_timeout)})

    async def clone(self) -> CloneResult:
        """initializes a git.Repo and returns the clone result. it either:

        - does not found a cloned repo locally and clones from remote url
        - finds a cloned repo locally and does not clone from remote.
        """
        logger.info(
            "Cloning repo from '{url}' to '{to_path}' (branch: '{branch}')",
            url=self.url,
            to_path=self.path,
            branch=self.branch_name,
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._attempt_clone_from_url)

    def _attempt_clone_from_url(self) -> CloneResult:
        """clones the repo from url or throws GitFailed."""
        env = self._provide_git_ssh_environment()
        _clone_func = partial(self._clone, env=env)
        _clone_with_retries = retry(**self._retry_config)(_clone_func)
        try:
            repo: Repo = _clone_with_retries()
        except (GitError, GitCommandError) as e:
            raise GitFailed(e)
        except RetryError as e:
            logger.exception("cannot clone policy repo: {error}", error=e)
            raise GitFailed(e)
        else:
            logger.info("Clone succeeded", repo_path=self.path)
            return CloneResult(repo)

    def _clone(self, env) -> Repo:
        try:
            return Repo.clone_from(
                url=self.url, to_path=self.path, branch=self.branch_name, env=env
            )
        except (GitError, GitCommandError) as e:
            logger.error("cannot clone policy repo: {error}", error=e)
            raise

    def _provide_git_ssh_environment(self):
        """provides git SSH configuration via GIT_SSH_COMMAND.

        the git ssh config will be provided only if the following conditions are met:
        - the repo url is a git ssh url
        - an ssh private key is provided in Repo Cloner __init__
        """
        if not is_ssh_repo_url(self.url) or self._ssh_key is None:
            return None  # no ssh config
        git_ssh_identity_file = self._save_ssh_key_to_pem_file(self._ssh_key)
        return {
            "GIT_SSH_COMMAND": f"ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes -i {git_ssh_identity_file}",
            "GIT_TRACE": "1",
            "GIT_CURL_VERBOSE": "1",
        }

    def _save_ssh_key_to_pem_file(self, key: str) -> Path:
        key = key.replace("_", "\n")
        if not key.endswith("\n"):
            key = key + "\n"  # pem file must end with newline
        key_path = os.path.expanduser(self._ssh_key_file_path)
        parent_directory = os.path.dirname(key_path)
        if not os.path.exists(parent_directory):
            os.makedirs(parent_directory, exist_ok=True)
        with open(key_path, "w") as f:
            f.write(key)
        os.chmod(key_path, 0o600)
        return Path(key_path)
