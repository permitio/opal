import hashlib
import os
import shutil
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, Optional, Tuple

import aiofiles.os
import aioredis
from ddtrace import tracer
from git import BadName, GitError, InvalidGitRepositoryError, Reference, Repo
from opal_common.async_utils import run_sync
from opal_common.git.bundle_maker import BundleMaker
from opal_common.logger import logger
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    SSHAuthData,
    UserPassAuthData,
)
from opal_common.synchronization.expiring_redis_lock import run_locked


class PolicyFetcherCallbacks:
    async def on_update(self, old_head: Optional[str], head: str):
        ...


class PolicyFetcher:
    def __init__(self, callbacks):
        self.callbacks = callbacks

    def fetch(self, hinted_hash: Optional[str] = None):
        raise NotImplementedError()


class RepoInterface:
    """Manages a git repo with gitpython."""

    @staticmethod
    def repo_branches(
        repo: Repo,
    ) -> Tuple[Dict[str, Reference], Dict[str, Dict[str, Reference]]]:
        local_branches = {}
        remote_branches: dict[str, dict[str, Reference]] = defaultdict(dict)
        for branch in repo.heads:
            local_branches[branch.name] = branch
        for remote in repo.remotes:
            for ref in remote.refs:
                branch_name = ref.name.split("/", 1)[1]
                remote_branches[remote.name][branch_name] = ref
        return local_branches, remote_branches

    @staticmethod
    def create_local_tracking_branch(
        repo: Repo, branch_name: str, remote_ref: Reference
    ) -> Reference:
        branch = repo.create_head(branch_name, remote_ref)
        branch.set_tracking_branch(remote_ref)
        logger.debug(
            f"Created local branch '{branch_name}', pointing to: {branch.commit.hexsha}"
        )
        return branch

    @staticmethod
    def create_local_branch_ref(
        repo: Repo,
        branch_name: str,
        remote_name: str,
        base_branch: Optional[str],
    ) -> Reference:
        local_branches, remote_branches = RepoInterface.repo_branches(repo)
        if branch_name in local_branches:
            logger.debug(
                f"No need to create local branch '{branch_name}': already exists!"
            )
            return local_branches[branch_name]
        if branch_name in remote_branches[remote_name]:
            return RepoInterface.create_local_tracking_branch(
                repo, branch_name, remote_branches[remote_name][branch_name]
            )
        elif base_branch is not None and base_branch in remote_branches[remote_name]:
            return RepoInterface.create_local_tracking_branch(
                repo, branch_name, remote_branches[remote_name][base_branch]
            )
        raise RuntimeError("Both branch and base branch were not found on remote")

    @staticmethod
    def has_remote_branch(repo: Repo, branch: str, remote: str) -> bool:
        try:
            repo.rev_parse(f"refs/remotes/{remote}/{branch}")
            return True
        except BadName:
            return False

    @staticmethod
    def get_commit_hash(repo: Repo, branch: str, remote: str) -> Optional[str]:
        try:
            commit = repo.rev_parse(f"refs/remotes/{remote}/{branch}")
            return commit.hexsha
        except BadName:
            return None

    @staticmethod
    def checkout_local_branch_from_remote(
        repo: Repo,
        branch_name: str,
        remote_name: str,
    ):
        ref = RepoInterface.create_local_branch_ref(
            repo, branch_name, remote_name, None
        )
        ref.checkout()

    @staticmethod
    def verify_found_repo_matches_remote(expected_remote_url: str, clone_path: str):
        """verifies that the repo we found in the directory matches the repo we
        are wishing to clone."""
        repo = Repo(clone_path)
        for remote in repo.remotes:
            if remote.url == expected_remote_url:
                logger.debug(
                    f"found target repo url is referred by remote: {remote.name}, url={remote.url}"
                )
                return
        error: str = f"Repo mismatch! No remote matches target url: {expected_remote_url}, found urls: {[remote.url for remote in repo.remotes]}"
        logger.error(error)
        raise ValueError(error)


class GitPolicyFetcher(PolicyFetcher):
    def __init__(
        self,
        base_dir: Path,
        scope_id: str,
        source: GitPolicyScopeSource,
        callbacks=PolicyFetcherCallbacks(),
        remote_name: str = "origin",
    ):
        super().__init__(callbacks)
        self._base_dir = GitPolicyFetcher.base_dir(base_dir)
        self._source = source
        self._repo_path = GitPolicyFetcher.repo_clone_path(base_dir, self._source)
        self._remote = remote_name
        self._scope_id = scope_id
        logger.info(
            f"Initializing git fetcher: scope_id={scope_id}, url={source.url}, branch={self._source.branch}, path={GitPolicyFetcher.source_id(source)}"
        )

    async def concurrent_fetch(self, redis: aioredis.Redis, *args, **kwargs):
        """makes sure the repo is already fetched and is up to date.

        A wrapper around fetch() to ensure that there are no concurrency
        issues when trying to fetch multiple scopes that are cloned to
        the same file system directory. We obtain safety with redis
        locks.
        """
        lock_name = GitPolicyFetcher.source_id(self._source)
        await run_locked(redis, lock_name, self.fetch(*args, **kwargs))

    async def fetch(self, hinted_hash: Optional[str] = None, force_fetch: bool = False):
        """makes sure the repo is already fetched and is up to date.

        - if no repo is found, the repo will be cloned.
        - if the repo is found and it is deemed out-of-date, the configured remote will be fetched.
        - if after a fetch new commits are detected, a callback will be triggered.
        - if the hinted commit hash is provided and is already found in the local clone
        we use this hint to avoid an necessary fetch.
        """
        await aiofiles.os.makedirs(str(self._base_dir), exist_ok=True)

        if self._repo_path.exists():
            if self._is_valid_repository(self._repo_path):
                logger.info("Repo found at {path}", path=self._repo_path)
                # This will raise a ValueError if it doesn't match (which won't
                # let OPAL startup), which is desirable because if it doesn't
                # it's definitely a misconfiguration and we want the admin to
                # notice immediately
                RepoInterface.verify_found_repo_matches_remote(
                    self._source.url, str(self._repo_path)
                )
                repo = Repo(str(self._repo_path))
                if not (
                    await self._should_fetch(
                        repo, hinted_hash=hinted_hash, force_fetch=force_fetch
                    )
                ):
                    logger.info("Skipping fetch")
                    return
                await self._fetch_and_notify_on_changes(repo)
                return

            # repo dir exists but invalid -> we must delete the directory
            logger.info("Deleting invalid repo: {path}", path=self._repo_path)
            shutil.rmtree(self._repo_path)

        # fallthrough to clean clone
        await self._clone()

    def _is_valid_repository(self, path: Path) -> bool:
        try:
            Repo(path)
            return True
        except InvalidGitRepositoryError:
            return False

    def _git_auth_data(self) -> Tuple[Dict[str, str], Optional[str]]:
        auth_data = self._source.auth
        if isinstance(auth_data, SSHAuthData):
            fd, path = tempfile.mkstemp()
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(auth_data.private_key)
            return {"GIT_SSH_COMMAND": f"ssh -i {path}"}, path
        if isinstance(auth_data, GitHubTokenAuthData):
            return {
                "GIT_ASKPASS": str(Path(__file__).parent / "git_authn.py"),
                "GIT_USERNAME": "git",
                "GIT_PASSWORD": auth_data.token,
            }, None
        if isinstance(auth_data, UserPassAuthData):
            return {
                "GIT_ASKPASS": str(Path(__file__).parent / "git_authn.py"),
                "GIT_USERNAME": auth_data.username,
                "GIT_PASSWORD": auth_data.password,
            }, None
        raise ValueError("Invalid authentication type.")

    @contextmanager
    def _git_auth_env(self) -> Generator[Dict[str, str], None, None]:
        env, key_path = self._git_auth_data()
        try:
            yield env
        finally:
            if key_path is not None:
                # TODO: Preload a key directly into an ssh-agent to avoid
                # storing it on the disk altogether
                # Attempt to securely erase the contents before deleting the key
                size = os.path.getsize(key_path)
                with open(key_path, "wb") as f:
                    f.write(b"\0" * size)
                os.unlink(key_path)

    def _clone_repo(self, url: str, path: str, branch: str) -> Repo:
        with self._git_auth_env() as env:
            return Repo.clone_from(url, path, branch=branch, env=env)

    async def _clone(self):
        logger.info(
            "Cloning repo at '{url}' to '{path}'",
            url=self._source.url,
            path=self._repo_path,
        )
        try:
            repo: Repo = await run_sync(
                self._clone_repo,
                self._source.url,
                str(self._repo_path),
                branch=self._source.branch,
            )
            logger.info(f"Clone completed: {self._source.url}")
            await self.callbacks.on_update(None, repo.head.commit.hexsha)
        except GitError:
            logger.exception(
                f"Could not clone repo at {self._source.url}, checkout branch={self._source.branch}"
            )

    def _get_valid_repo_at(self, path: str) -> Optional[Repo]:
        try:
            return Repo(path)
        except InvalidGitRepositoryError:
            logger.warning("Invalid repo at: {path}", path=path)
            return None

    async def _should_fetch(
        self,
        repo: Repo,
        hinted_hash: Optional[str] = None,
        force_fetch: bool = False,
    ) -> bool:
        if force_fetch:
            logger.info("Force-fetch was requested")
            return True  # must fetch

        if not RepoInterface.has_remote_branch(repo, self._source.branch, self._remote):
            logger.info(
                "Target branch was not found in local clone, re-fetching the remote"
            )
            return True  # missing branch

        if hinted_hash is not None:
            try:
                repo.rev_parse(hinted_hash)
                return False  # hinted commit was found, no need to fetch
            except BadName:
                logger.info(
                    "Hinted commit hash was not found in local clone, re-fetching the remote"
                )
                return True  # hinted commit was not found

        # by default, we try to avoid re-fetching the repo for performance
        return False

    async def _fetch_and_notify_on_changes(self, repo: Repo):
        old_revision = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        logger.info(f"Fetching remote: {self._remote} ({self._source.url})")
        with self._git_auth_env() as env:
            with repo.git.custom_environment(**env):
                await run_sync(repo.remotes[self._remote].fetch)
        logger.info(f"Fetch completed: {self._source.url}")
        new_revision = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        if new_revision is None:
            logger.error(f"Did not find target branch on remote: {self._source.branch}")
            return
        await self.callbacks.on_update(old_revision, new_revision)

    def _get_current_branch_head(self) -> str:
        repo = Repo(str(self._repo_path))
        head_commit_hash = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        if not head_commit_hash:
            logger.error("Could not find current branch head")
            raise ValueError("Could not find current branch head")
        return head_commit_hash

    def make_bundle(self, base_hash: Optional[str] = None) -> PolicyBundle:
        with tracer.trace("make_bundle"):
            repo = Repo(str(self._repo_path))
            bundle_maker = BundleMaker(
                repo,
                {Path(p) for p in self._source.directories},
                extensions=self._source.extensions,
                root_manifest_path=self._source.manifest,
            )
            current_head_commit = repo.commit(self._get_current_branch_head())

            if not base_hash:
                return bundle_maker.make_bundle(current_head_commit)
            else:
                try:
                    base_commit = repo.commit(base_hash)
                    return bundle_maker.make_diff_bundle(
                        base_commit, current_head_commit
                    )
                except ValueError:
                    return bundle_maker.make_bundle(current_head_commit)

    @staticmethod
    def source_id(source: GitPolicyScopeSource) -> str:
        return hashlib.sha256(source.url.encode("utf-8")).hexdigest()

    @staticmethod
    def base_dir(base_dir: Path) -> Path:
        return base_dir / "git_sources"

    @staticmethod
    def repo_clone_path(base_dir: Path, source: GitPolicyScopeSource) -> Path:
        return GitPolicyFetcher.base_dir(base_dir) / GitPolicyFetcher.source_id(source)
