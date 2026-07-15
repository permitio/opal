import asyncio
import codecs
import datetime
import hashlib
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, cast

import aiofiles.os
import pygit2
from ddtrace import tracer
from git import Repo
from opal_common.async_utils import run_sync
from opal_common.git_utils.bundle_maker import BundleMaker
from opal_common.http_utils import redact_url
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
                    f"found target repo url is referred by remote: {remote.name}, url={redact_url(remote.url)}"
                )
                return
        error: str = f"Repo mismatch! No remote matches target url: {redact_url(expected_remote_url)}, found urls: {[redact_url(remote.url) for remote in repo.remotes]}"
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
        self._source_id = GitPolicyFetcher.source_id(self._source)
        self._auth_callbacks = GitCallback(self._source)
        self._repo_path = self._base_dir / self._source_id
        self._remote = remote_name
        self._scope_id = scope_id
        logger.debug(
            f"Initializing git fetcher: scope_id={scope_id}, url={redact_url(source.url)}, branch={self._source.branch}, source_id={self._source_id}"
        )

    @staticmethod
    @asynccontextmanager
    async def lock_source(source_id: str):
        """Serialize all mutation of a source's clone dir and cached handles.

        Locks are minted on demand into ``repo_locks`` (asyncio.Lock: process-
        local but fair, unlike the previous file-based lock). A scope delete
        pops the dict entry while holding the lock, so after acquiring we must
        re-check that ``repo_locks`` still maps ``source_id`` to the lock we
        acquired — a waiter woken after a delete would otherwise proceed under
        the stale lock, unserialized against holders of the freshly-minted one.
        """
        while True:
            lock = GitPolicyFetcher.repo_locks.setdefault(source_id, asyncio.Lock())
            async with lock:
                if GitPolicyFetcher.repo_locks.get(source_id) is lock:
                    yield
                    return

    async def _was_fetched_after(self, t: datetime.datetime):
        last_fetched = GitPolicyFetcher.repos_last_fetched.get(self._source_id, None)
        if last_fetched is None:
            return False
        return last_fetched > t

    async def fetch_and_notify_on_changes(
        self,
        hinted_hash: Optional[str] = None,
        force_fetch: bool = False,
        req_time: datetime.datetime = None,
    ):
        """Makes sure the repo is already fetched and is up to date.

        - if no repo is found, the repo will be cloned.
        - if the repo is found and it is deemed out-of-date, the configured remote will be fetched.
        - if after a fetch new commits are detected, a callback will be triggered.
        - if the hinted commit hash is provided and is already found in the local clone
        we use this hint to avoid an necessary fetch.
        """
        async with GitPolicyFetcher.lock_source(self._source_id):
            with tracer.trace(
                "git_policy_fetcher.fetch_and_notify_on_changes",
                resource=self._scope_id,
            ):
                if self._discover_repository(self._repo_path):
                    logger.debug("Repo found at {path}", path=self._repo_path)
                    # The probe opens/parses a fresh Repository handle from
                    # disk — off the event loop so a slow disk can't stall
                    # every other request being served on this worker.
                    repo = await run_sync(self._get_valid_repo)
                    if repo is not None:
                        should_fetch = await self._should_fetch(
                            repo,
                            hinted_hash=hinted_hash,
                            force_fetch=force_fetch,
                            req_time=req_time,
                        )
                        if should_fetch:
                            logger.debug(
                                f"Fetching remote (force_fetch={force_fetch}): {self._remote} ({redact_url(self._source.url)})"
                            )
                            # Record the START time but write it only on
                            # success: a failed fetch must not look "fresh"
                            # to _was_fetched_after(), or it suppresses the
                            # forced refresh a webhook just asked for. The
                            # start time (not completion) is what req_time
                            # comparisons need: a fetch that STARTED after
                            # the request already satisfies it.
                            fetch_started = datetime.datetime.now()
                            await run_sync(
                                repo.remotes[self._remote].fetch,
                                callbacks=self._auth_callbacks,
                            )
                            GitPolicyFetcher.repos_last_fetched[
                                self._source_id
                            ] = fetch_started
                            logger.debug(
                                f"Fetch completed: {redact_url(self._source.url)}"
                            )

                        # New commits might be present because of a previous fetch made by another scope
                        await self._notify_on_changes(repo)
                        return
                    else:
                        # repo dir exists but invalid -> drop the cached handle
                        # FIRST (it is the thing judging the dir invalid; kept,
                        # it would re-invalidate the fresh clone on every sync
                        # -> infinite re-clone loop), then delete the directory.
                        logger.warning(
                            "Deleting invalid repo: {path}", path=self._repo_path
                        )
                        GitPolicyFetcher.forget_repo(str(self._repo_path))
                        try:
                            await run_sync(shutil.rmtree, str(self._repo_path))
                        except FileNotFoundError:
                            pass  # already gone — the intended end state
                        except OSError as e:
                            logger.warning(
                                f"Failed to remove clone dir "
                                f"{self._repo_path}: {e!r}"
                            )
                else:
                    logger.info("Repo not found at {path}", path=self._repo_path)

                # fallthrough to clean clone
                await self._clone()

    def _discover_repository(self, path: Path) -> bool:
        git_path: Path = path / ".git"
        return discover_repository(str(path)) and git_path.exists()

    async def _clone(self):
        if self._repo_path.exists():
            # A failed/interrupted clone leaves a partial dir;
            # clone_repository refuses a non-empty destination, which would
            # wedge every retry for this source.
            try:
                await run_sync(shutil.rmtree, str(self._repo_path))
            except FileNotFoundError:
                pass  # already gone — the intended end state
            except OSError as e:
                logger.warning(f"Failed to remove clone dir {self._repo_path}: {e!r}")
        logger.info(
            "Cloning repo at '{url}' to '{path}'",
            url=redact_url(self._source.url),
            path=self._repo_path,
        )
        # Same start-time rule as the fetch path above: the clone's
        # negotiation reflects remote state at clone START, so that is the
        # timestamp req_time comparisons need.
        clone_started = datetime.datetime.now()
        try:
            repo: Repository = await run_sync(
                clone_repository,
                self._source.url,
                str(self._repo_path),
                callbacks=self._auth_callbacks,
            )
        except pygit2.GitError:
            logger.exception(f"Could not clone repo at {redact_url(self._source.url)}")
        else:
            logger.info(f"Clone completed: {redact_url(self._source.url)}")
            # Cache the fresh handle so the next sync's _get_repo() reuses it
            # instead of reopening (or hitting a stale predecessor).
            GitPolicyFetcher.repos[str(self._repo_path)] = repo
            # A reclone just downloaded current remote state — record it so
            # _was_fetched_after() doesn't force a redundant fetch next cycle.
            GitPolicyFetcher.repos_last_fetched[self._source_id] = clone_started
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
            # A clone can be discoverable yet unusable: refs and config
            # intact but the object store gutted (crash mid-gc, disk
            # corruption). A fetch then negotiates "up to date" against the
            # intact refs and downloads nothing, so without this check the
            # scope serves 500s forever with no self-heal. Validate that the
            # tracked branch's head object is actually readable FROM DISK:
            # the check must use a short-lived fresh handle, because the
            # cached warm handle keeps deleted pack files readable through
            # its open mmaps (unlink does not invalidate them) and would
            # report the object as present. Partial corruption deeper in
            # the tree is NOT caught here (that would need fsck-grade
            # checks).
            probe = Repository(str(self._repo_path))
            try:
                try:
                    ref = probe.lookup_reference(
                        f"refs/remotes/{self._remote}/{self._source.branch}"
                    )
                except KeyError:
                    # Branch not fetched yet — the fetch path handles that.
                    return repo
                if probe.get(ref.target) is None:
                    logger.warning(
                        "Repo at {path} has refs but an unreadable object "
                        "store (missing head object) — treating as invalid",
                        path=self._repo_path,
                    )
                    return None
                return repo
            finally:
                probe.free()
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

    @property
    def local_branch_name(self) -> str:
        # Use the scope id as local branch name, so different scopes could track the same remote branch separately
        branch_name_unescaped = f"scopes/{self._scope_id}"
        if reference_is_valid_name(branch_name_unescaped):
            return branch_name_unescaped

        # if scope id can't be used as a gitref (e.g invalid chars), use its hex representation
        return f"scopes/{self._scope_id.encode().hex()}"

    async def _notify_on_changes(self, repo: Repository):
        # Get the latest commit hash of the target branch
        new_revision = RepoInterface.get_commit_hash(
            repo, self._source.branch, self._remote
        )
        if new_revision is None:
            logger.error(f"Did not find target branch on remote: {self._source.branch}")
            return

        # Get the previous commit hash of the target branch
        local_branch = RepoInterface.get_local_branch(repo, self.local_branch_name)
        if local_branch is None:
            # First sync of a new branch (the first synced branch in this repo was set by the clone (see `checkout_branch`))
            old_revision = None
            local_branch = RepoInterface.create_local_branch_ref(
                repo, self.local_branch_name, self._remote, self._source.branch
            )
        else:
            old_revision = local_branch.target.hex

        await self.callbacks.on_update(old_revision, new_revision)

        # Bring forward local branch (a bit like "pull"), so we won't detect changes again
        local_branch.set_target(new_revision)

    def _get_current_branch_head(self) -> str:
        # Opened fresh per call instead of using the shared cached handle:
        # this runs on executor threads (run_sync(make_bundle) in the policy-
        # bundle route) and outside lock_source, where the cached handle can
        # be free()'d concurrently by a scope delete or invalid-repo recovery.
        # asyncio locks don't exclude executor threads — sharing the handle
        # here is a use-after-free. Same fresh-probe pattern as
        # _get_valid_repo's disk-truth check.
        repo = Repository(str(self._repo_path))
        try:
            head_commit_hash = RepoInterface.get_commit_hash(
                repo, self._source.branch, self._remote
            )
        finally:
            free = getattr(repo, "free", None)
            if callable(free):
                free()
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

    @staticmethod
    def forget_repo(path: str) -> None:
        """Drop the cached repository for a clone path and release its handles.

        The cached ``pygit2.Repository`` keeps OS file descriptors and mmapped
        pack indexes open; without this, a deleted scope's repo pins memory and
        inodes for the lifetime of the process even after the clone is removed.
        ``Repository.free()`` is called only when available (the pinned pygit2
        always has it; the guard defends against test doubles and future API
        changes); otherwise the dropped reference is reclaimed by GC.
        """
        repo = GitPolicyFetcher.repos.pop(path, None)
        if repo is None:
            return
        free = getattr(repo, "free", None)
        if callable(free):
            try:
                free()
            except Exception as e:
                logger.warning(
                    f"pygit2 Repository.free() failed for {path}: {e!r}; "
                    "relying on GC to release the handles"
                )


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
