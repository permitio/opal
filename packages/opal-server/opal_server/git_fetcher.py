import hashlib
import shutil
from pathlib import Path
from typing import Optional, cast

import aiofiles.os
import aioredis
import pygit2
from git import Repo
from opal_common.async_utils import run_sync
from opal_common.git.bundle_maker import BundleMaker
from opal_common.logger import logger
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    SSHAuthData,
)
from pygit2 import (
    KeypairFromMemory,
    RemoteCallbacks,
    Repository,
    Username,
    UserPass,
    clone_repository,
    discover_repository,
)


class PolicyFetcherCallbacks:
    async def on_update(self, old_head: Optional[str], head: str):
        pass


class PolicyFetcher:
    def __init__(self, callbacks):
        self.callbacks = callbacks

    def fetch(self, hinted_hash: Optional[str] = None):
        raise NotImplementedError()


class RepoInterface:
    """Manages a git repo with pygit2."""

    @staticmethod
    def create_local_branch_ref(
        repo: Repository,
        branch_name: str,
        remote_name: str,
        base_branch: str,
    ) -> pygit2.Reference:
        if branch_name not in repo.branches.local:
            remote_branch = f"{remote_name}/{branch_name}"
            base_remote_branch = f"{remote_name}/{base_branch}"
            if remote_branch in repo.branches.remote:
                (commit, _) = repo.resolve_refish(remote_branch)
            elif repo.branches.remote.get(base_remote_branch) is not None:
                (commit, _) = repo.resolve_refish(base_remote_branch)
            else:
                raise RuntimeError(
                    "Both branch and base branch were not found on remote"
                )
            logger.debug(
                f"Created local branch '{branch_name}', pointing to: {commit.hex}"
            )
            return repo.create_reference(f"refs/heads/{branch_name}", commit.hex)
        else:
            logger.debug(
                f"No need to create local branch '{branch_name}': already exists!"
            )
            return repo.references[f"refs/heads/{branch_name}"]

    @staticmethod
    def has_remote_branch(repo: Repository, branch: str, remote: str) -> bool:
        try:
            repo.lookup_reference(f"refs/remotes/{remote}/{branch}")
            return True
        except KeyError:
            return False

    @staticmethod
    def get_commit_hash(repo: Repository, branch: str, remote: str) -> Optional[str]:
        try:
            (commit, _) = repo.resolve_refish(f"{remote}/{branch}")
            return commit.hex
        except (pygit2.GitError, KeyError):
            return None

    @staticmethod
    def checkout_local_branch_from_remote(
        repo: Repository,
        branch_name: str,
        remote_name: str,
    ):
        ref = RepoInterface.create_local_branch_ref(repo, branch_name, remote_name)
        repo.checkout(ref)

    @staticmethod
    def verify_found_repo_matches_remote(
        expected_remote_url: str, clone_path: str
    ) -> Repository:
        """verifies that the repo we found in the directory matches the repo we
        are wishing to clone."""
        repo = Repository(clone_path)
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
        self._auth_callbacks = GitCallback(self._source)
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
        lock = redis.lock(lock_name)
        try:
            logger.info(f"Trying to acquire redis lock: {lock_name}")
            await lock.acquire()
            logger.info(f"Acquired lock: {lock_name}")
            await self.fetch(*args, **kwargs)
        finally:
            await lock.release()
            logger.info(f"Released lock: {lock_name}")

    async def fetch(self, hinted_hash: Optional[str] = None, force_fetch: bool = False):
        """makes sure the repo is already fetched and is up to date.

        - if no repo is found, the repo will be cloned.
        - if the repo is found and it is deemed out-of-date, the configured remote will be fetched.
        - if after a fetch new commits are detected, a callback will be triggered.
        - if the hinted commit hash is provided and is already found in the local clone
        we use this hint to avoid an necessary fetch.
        """
        await aiofiles.os.makedirs(str(self._base_dir), exist_ok=True)

        if self._discover_repository(self._repo_path):
            logger.info("Repo found at {path}", path=self._repo_path)
            RepoInterface.verify_found_repo_matches_remote(
                self._source.url, str(self._repo_path)
            )
            repo = self._get_valid_repo_at(str(self._repo_path))
            if repo is not None:
                if not (
                    await self._should_fetch(
                        repo, hinted_hash=hinted_hash, force_fetch=force_fetch
                    )
                ):
                    logger.info("Skipping fetch")
                    return
                await self._fetch_and_notify_on_changes(repo)
                return
            else:
                # repo dir exists but invalid -> we must delete the directory
                logger.info("Deleting invalid repo: {path}", path=self._repo_path)
                shutil.rmtree(self._repo_path)
        else:
            logger.info("Repo not found at {path}", path=self._repo_path)

        # fallthrough to clean clone
        await self._clone()

    def _discover_repository(self, path: Path) -> bool:
        git_path: Path = path / ".git"
        return discover_repository(str(path)) and git_path.exists()

    async def _clone(self):
        logger.info(
            "Cloning repo at '{url}' to '{path}'",
            url=self._source.url,
            path=self._repo_path,
        )
        try:
            repo: Repository = await run_sync(
                clone_repository,
                self._source.url,
                str(self._repo_path),
                callbacks=self._auth_callbacks,
                checkout_branch=self._source.branch,
            )
        except pygit2.GitError:
            logger.exception(
                f"Could not clone repo at {self._source.url}, checkout branch={self._source.branch}"
            )
        else:
            logger.info(f"Clone completed: {self._source.url}")
            await self.callbacks.on_update(None, repo.head.target.hex)

    def _get_valid_repo_at(self, path: str) -> Optional[Repository]:
        try:
            return Repository(path)
        except pygit2.GitError:
            logger.warning("Invalid repo at: {path}", path=path)
            return None

    async def _should_fetch(
        self,
        repo: Repository,
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
                _ = repo.revparse_single(hinted_hash)
                return False  # hinted commit was found, no need to fetch
            except KeyError:
                logger.info(
                    "Hinted commit hash was not found in local clone, re-fetching the remote"
                )
                return True  # hinted commit was not found

        # by default, we try to avoid re-fetching the repo for performance
        return False

    async def _fetch_and_notify_on_changes(self, repo: Repository):
        old_revision = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        logger.info(f"Fetching remote: {self._remote} ({self._source.url})")
        await run_sync(repo.remotes[self._remote].fetch, callbacks=self._auth_callbacks)
        logger.info(f"Fetch completed: {self._source.url}")
        new_revision = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        if new_revision is None:
            logger.error(f"Did not find target branch on remote: {self._source.branch}")
            return
        await self.callbacks.on_update(old_revision, new_revision)

    def _get_current_branch_head(self) -> str:
        repo = Repository(str(self._repo_path))
        head_commit_hash = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        if not head_commit_hash:
            logger.error("Could not find current branch head")
            raise ValueError("Could not find current branch head")
        return head_commit_hash

    def make_bundle(self, base_hash: Optional[str] = None) -> PolicyBundle:
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
                return bundle_maker.make_diff_bundle(base_commit, current_head_commit)
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


class GitCallback(RemoteCallbacks):
    def __init__(self, source: GitPolicyScopeSource):
        super().__init__()
        self._source = source

    def credentials(self, url, username_from_url, allowed_types):
        if isinstance(self._source.auth, SSHAuthData):
            auth = cast(SSHAuthData, self._source.auth)

            ssh_key = dict(
                username=username_from_url,
                pubkey=auth.public_key or "",
                privkey=auth.private_key,
                passphrase="",
            )
            return KeypairFromMemory(**ssh_key)
        if isinstance(self._source.auth, GitHubTokenAuthData):
            auth = cast(GitHubTokenAuthData, self._source.auth)

            return UserPass(username="git", password=auth.token)

        return Username(username_from_url)
