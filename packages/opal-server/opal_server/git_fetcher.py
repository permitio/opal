import asyncio
import codecs
import datetime
import hashlib
import shutil
import time
import os
import subprocess
from pathlib import Path
from typing import Optional, cast

import aiofiles.os
import pygit2
from ddtrace import tracer
from git import Repo
from opal_common.async_utils import run_sync
from opal_common.git_utils.bundle_maker import BundleMaker
from opal_common.logger import logger
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    SSHAuthData,
)
from opal_common.synchronization.named_lock import NamedLock
from opal_server.config import opal_server_config
from pygit2 import (
    KeypairFromMemory,
    RemoteCallbacks,
    Repository,
    Username,
    UserPass,
    clone_repository,
    discover_repository,
    reference_is_valid_name,
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
            base_remote_branch = f"{remote_name}/{base_branch}"
            if repo.branches.remote.get(base_remote_branch) is not None:
                (commit, _) = repo.resolve_refish(base_remote_branch)
            else:
                raise RuntimeError("Base branch was not found on remote")
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
    def get_local_branch(repo: Repository, branch: str) -> Optional[pygit2.Reference]:
        try:
            return repo.lookup_reference(f"refs/heads/{branch}")
        except KeyError:
            return None

    @staticmethod
    def get_commit_hash(repo: Repository, branch: str, remote: str) -> Optional[str]:
        try:
            (commit, _) = repo.resolve_refish(f"{remote}/{branch}")
            return commit.hex
        except (pygit2.GitError, KeyError):
            return None

    @staticmethod
    def verify_found_repo_matches_remote(
        repo: Repository,
        expected_remote_url: str,
    ) -> Repository:
        """Verifies that the repo we found in the directory matches the repo we
        are wishing to clone."""
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
    repo_locks = {}
    repos = {}
    repos_last_fetched = {}

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
        logger.debug(
            f"Initializing git fetcher: scope_id={scope_id}, url={source.url}, branch={self._source.branch}, path={GitPolicyFetcher.source_id(source)}"
        )

    async def _get_repo_lock(self):
        src_id = GitPolicyFetcher.source_id(self._source)
        lock = GitPolicyFetcher.repo_locks[src_id] = GitPolicyFetcher.repo_locks.get(
            src_id, asyncio.Lock()
        )
        return lock

    async def _was_fetched_after(self, t: datetime.datetime):
        last_fetched = GitPolicyFetcher.repos_last_fetched.get(self.source_id, None)
        if last_fetched is None:
            return False
        return last_fetched > t

    async def _attempt_atomic_sync(self, repo_path: Path, hinted_hash: Optional[str], force_fetch: bool, req_time: datetime.datetime):
        """
        Inner atomic function to handle the sync logic.
        Isolating this allows for specific 'rollback' behaviors.
        """
        if self._discover_repository(repo_path):
            logger.debug("Repo found at {path}", path=repo_path)
            repo = self._get_valid_repo()

            if repo is not None:
                should_fetch = await self._should_fetch(
                    repo,
                    hinted_hash=hinted_hash,
                    force_fetch=force_fetch,
                    req_time=req_time,
                )
                if should_fetch:
                    logger.debug(f"Fetching remote: {self._remote} ({self._source.url})")
                    GitPolicyFetcher.repos_last_fetched[self.source_id] = datetime.datetime.now()

                    await run_sync(
                        repo.remotes[self._remote].fetch,
                        callbacks=self._auth_callbacks,
                    )

                await self._notify_on_changes(repo)
                return
            else:
                raise pygit2.GitError("Invalid repository metadata")
        else:
            await self._clone()

    def _perform_soft_cleanup(self, repo_path: Path):
        """
        Targets specific corrupted states like stale lock files or broken symlinks.
        Avoids expensive full re-clones.
        """
        logger.info(f"Attempting soft cleanup for repo at {repo_path}")

        # 1. Handle Symlinks specifically (Issue #634)
        if os.path.islink(repo_path):
            logger.warning(f"Removing broken or stale symlink at {repo_path}")
            repo_path.unlink()
            return

        # 2. Handle Git Lock Files - fixing the state instead of deleting
        lock_files = [
            repo_path / ".git" / "index.lock",
            repo_path / ".git" / "shallow.lock",
            repo_path / ".git" / "config.lock",
        ]

        for lock_file in lock_files:
            if lock_file.exists():
                try:
                    lock_file.unlink()
                    logger.info(f"Removed stale git lock file: {lock_file}")
                except Exception as e:
                    logger.error(f"Could not remove lock file {lock_file}: {e}")

    async def fetch_and_notify_on_changes(
        self,
        hinted_hash: Optional[str] = None,
        force_fetch: bool = False,
        req_time: datetime.datetime = None,
    ):
        repo_lock = await self._get_repo_lock()
        async with repo_lock:
            try:
                with tracer.trace(
                    "git_policy_fetcher.fetch_and_notify_on_changes",
                    resource=self._scope_id,
                ):
                    # Call atomic helper
                    await self._attempt_atomic_sync(self._repo_path, hinted_hash, force_fetch, req_time)

            except (pygit2.GitError, KeyError, subprocess.CalledProcessError) as git_err:
                # Dedicated rollback: try to fix corrupted state instead of deleting
                logger.warning(f"Git error detected: {git_err}. Attempting soft recovery.")
                self._perform_soft_cleanup(self._repo_path)
                raise git_err

            except Exception as e:
                # Broad rollback only as a last resort
                logger.error(f"Critical failure syncing repo: {e}. Falling back to full cleanup.")
                if self._repo_path.exists() or os.path.islink(self._repo_path):
                    if self._repo_path.is_symlink():
                        self._repo_path.unlink()
                    else:
                        shutil.rmtree(self._repo_path, ignore_errors=True)

                repo_path_str = str(self._repo_path)
                GitPolicyFetcher.repos.pop(repo_path_str, None)
                raise e

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
            )
        except pygit2.GitError:
            logger.exception(f"Could not clone repo at {self._source.url}")
            raise
        else:
            logger.info(f"Clone completed: {self._source.url}")
            await self._notify_on_changes(repo)

    def _get_repo(self) -> Repository:
        path = str(self._repo_path)
        if path not in GitPolicyFetcher.repos:
            GitPolicyFetcher.repos[path] = Repository(path)
        return GitPolicyFetcher.repos[path]

    def _get_valid_repo(self) -> Optional[Repository]:
        try:
            repo = self._get_repo()
            RepoInterface.verify_found_repo_matches_remote(repo, self._source.url)
            return repo
        except pygit2.GitError:
            logger.warning("Invalid repo at: {path}", path=self._repo_path)
            return None

    async def _should_fetch(
        self,
        repo: Repository,
        hinted_hash: Optional[str] = None,
        force_fetch: bool = False,
        req_time: datetime.datetime = None,
    ) -> bool:
        if force_fetch:
            if req_time is not None and await self._was_fetched_after(req_time):
                logger.info(
                    "Repo was fetched after refresh request, override force_fetch with False"
                )
            else:
                return True

        if not RepoInterface.has_remote_branch(repo, self._source.branch, self._remote):
            logger.info(
                "Target branch was not found in local clone, re-fetching the remote"
            )
            return True

        if hinted_hash is not None:
            try:
                _ = repo.revparse_single(hinted_hash)
                return False
            except KeyError:
                logger.info(
                    "Hinted commit hash was not found in local clone, re-fetching the remote"
                )
                return True

        return False

    @property
    def local_branch_name(self) -> str:
        branch_name_unescaped = f"scopes/{self._scope_id}"
        if reference_is_valid_name(branch_name_unescaped):
            return branch_name_unescaped
        return f"scopes/{self._scope_id.encode().hex()}"

    async def _notify_on_changes(self, repo: Repository):
        new_revision = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        if new_revision is None:
            logger.error(f"Did not find target branch on remote: {self._source.branch}")
            return

        local_branch = RepoInterface.get_local_branch(repo, self.local_branch_name)
        if local_branch is None:
            old_revision = None
            local_branch = RepoInterface.create_local_branch_ref(
                repo, self.local_branch_name, self._remote, self._source.branch
            )
        else:
            old_revision = local_branch.target.hex

        await self.callbacks.on_update(old_revision, new_revision)
        local_branch.set_target(new_revision)

    def _get_current_branch_head(self) -> str:
        repo = self._get_repo()
        head_commit_hash = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        if not head_commit_hash:
            logger.error("Could not find current branch head")
            raise ValueError("Could not find current branch head")
        return head_commit_hash

    @tracer.wrap("git_policy_fetcher.make_bundle")
    def make_bundle(self, base_hash: Optional[str] = None) -> PolicyBundle:
        repo = Repo(str(self._repo_path))
        bundle_maker = BundleMaker(
            repo,
            {Path(p) for p in self._source.directories},
            extensions=self._source.extensions,
            root_manifest_path=self._source.manifest,
            bundle_ignore=self._source.bundle_ignore,
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
        base = hashlib.sha256(source.url.encode("utf-8")).hexdigest()
        index = (
            hashlib.sha256(source.branch.encode("utf-8")).digest()[0]
            % opal_server_config.SCOPES_REPO_CLONES_SHARDS
        )
        return f"{base}-{index}"

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
