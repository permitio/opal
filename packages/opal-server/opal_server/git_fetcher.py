import shutil
from pathlib import Path
from typing import Optional, cast

import aiofiles.os
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

    def fetch(self):
        pass


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
    def checkout_local_branch_from_remote(
        repo: Repository,
        branch_name: str,
        remote_name: str,
    ):
        ref = RepoInterface.create_local_branch_ref(repo, branch_name, remote_name)
        repo.checkout(ref)

    @staticmethod
    def verify_found_repo_matches_origin(
        origin_url: str, clone_path: str
    ) -> Repository:
        """verifies that the repo we found in the directory matches the repo we
        are wishing to clone."""
        repo = Repository(clone_path)
        for remote in repo.remotes:
            if remote.url == origin_url:
                logger.debug(
                    f"found target repo url is referred by remote: {remote.name}, url={remote.url}"
                )
                return
        error: str = f"Repo mismatch! No remote matches target url: {origin_url}, found urls: {[remote.url for remote in repo.remotes]}"
        logger.error(error)
        raise ValueError(error)


class GitPolicyFetcher(PolicyFetcher):
    def __init__(
        self,
        base_dir: Path,
        scope_id: str,
        source: GitPolicyScopeSource,
        callbacks=PolicyFetcherCallbacks(),
    ):
        super().__init__(callbacks)
        self._base_dir = opal_scopes_dest_dir(base_dir)
        self._source = source
        self._auth_callbacks = GitCallback(self._source)
        self._repo_path = self._base_dir / scope_id

    async def fetch(self):
        await aiofiles.os.makedirs(str(self._base_dir), exist_ok=True)

        if self._discover_repository(self._repo_path):
            logger.debug(f"repo found at {self._repo_path}")
            repo = self._get_valid_repo_at(str(self._repo_path))
            if repo is not None:
                return await self._pull(repo)
            else:
                # repo dir exists but invalid -> we must delete the directory
                shutil.rmtree(self._repo_path)

        # fallthrough to clean clone
        return await self._clone()

    def _discover_repository(self, path: Path) -> bool:
        git_path: Path = path / ".git"
        return discover_repository(str(path)) and git_path.exists()

    async def _clone(self):
        logger.info("Cloning scope to {path}", path=self._repo_path)
        repo: Repository = await run_sync(
            clone_repository,
            self._source.url,
            str(self._repo_path),
            callbacks=self._auth_callbacks,
            checkout_branch=self._source.branch,
        )
        await self.callbacks.on_update(None, repo.head.target.hex)

    def _get_valid_repo_at(self, path: str) -> Optional[Repository]:
        RepoInterface.verify_found_repo_matches_origin(self._source.url, path)
        logger.info("Checking for new commits in {path}", path=path)
        try:
            return Repository(path)
        except pygit2.GitError:
            logger.error("invalid repo at: {path}", path=path)
            return None

    async def _pull(self, repo: Repository):
        old_revision = repo.head.target.hex
        await run_sync(repo.remotes["origin"].fetch, callbacks=self._auth_callbacks)
        repo.checkout(
            repo.references[f"refs/remotes/origin/{self._source.branch}"].resolve().name
        )
        await self.callbacks.on_update(old_revision, repo.head.target.hex)

    def make_bundle(self, base_hash: Optional[str] = None) -> PolicyBundle:
        repo = Repo(str(self._repo_path))

        bundle_maker = BundleMaker(
            repo,
            {Path(p) for p in self._source.directories},
            extensions=self._source.extensions,
            root_manifest_path=self._source.manifest,
        )

        if not base_hash:
            return bundle_maker.make_bundle(repo.head.commit)
        else:
            try:
                old_commit = repo.commit(base_hash)
                return bundle_maker.make_diff_bundle(old_commit, repo.head.commit)
            except ValueError:
                return bundle_maker.make_bundle(repo.head.commit)


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


def opal_scopes_dest_dir(base_dir: Path):
    return base_dir / "scopes"
