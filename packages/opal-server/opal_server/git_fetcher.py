import asyncio
import codecs
import datetime
import hashlib
import os
import shutil
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import thread as cf_thread
from functools import partial
from pathlib import Path
from typing import Optional, cast

import aiofiles.os
import pygit2
from ddtrace import tracer
from git import Repo
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

_git_executor: Optional[ThreadPoolExecutor] = None

# Source ids whose scope git op (clone/fetch) is still running on a pool thread
# — including one that already exceeded its timeout but whose blocking pygit2
# call has not yet returned. Guarded by a lock because it is cleared from the
# pool thread (see ``run_in_git_executor``) and read/written from the event
# loop. Used to guarantee at most one live git op per repository, since pygit2
# ``Repository`` objects are not thread-safe.
_git_busy: set = set()
_git_busy_lock = threading.Lock()


class _DaemonThreadPoolExecutor(ThreadPoolExecutor):
    """A ``ThreadPoolExecutor`` whose worker threads are daemon threads.

    A scope git op can stay blocked in a libgit2 network call well past our
    soft timeout. With the stdlib's non-daemon workers, ``concurrent.futures``'
    atexit handler would ``join()`` such a thread and hang interpreter shutdown
    until the OS network timeout fires. Daemon workers let the process exit
    promptly; abandoning an in-flight fetch at exit is safe (libgit2 stages
    objects in a temp pack and swaps refs atomically under lockfiles, and a
    half-written clone dir is detected as invalid and re-cloned on next boot).

    Only thread creation is customised, mirroring CPython's
    ``_adjust_thread_count``. If a future CPython changes the internals we rely
    on, we fall back to the stdlib (non-daemon) behaviour.
    """

    def _adjust_thread_count(self) -> None:  # pragma: no cover - thread mgmt
        if not hasattr(cf_thread, "_worker") or not hasattr(
            cf_thread, "_threads_queues"
        ):
            return super()._adjust_thread_count()
        # If idle threads are available, don't spin up new ones.
        if self._idle_semaphore.acquire(timeout=0):
            return

        def weakref_cb(_, q=self._work_queue):
            q.put(None)

        num_threads = len(self._threads)
        if num_threads < self._max_workers:
            thread_name = "%s_%d" % (self._thread_name_prefix or self, num_threads)
            t = threading.Thread(
                name=thread_name,
                target=cf_thread._worker,
                args=(
                    weakref.ref(self, weakref_cb),
                    self._work_queue,
                    self._initializer,
                    self._initargs,
                ),
                daemon=True,
            )
            t.start()
            self._threads.add(t)
            cf_thread._threads_queues[t] = self._work_queue


def _get_git_executor() -> ThreadPoolExecutor:
    """Lazily build the dedicated pool for scope git operations.

    Isolated from the default executor so a hung clone/fetch can never starve
    bundle serving or other server work. Workers are daemon threads so a
    lingering (timed-out) git op cannot block interpreter shutdown.

    ``SCOPES_GIT_MAX_WORKERS`` is read once on first use; the executor is then
    cached for the process lifetime. It is reset after ``fork`` (see
    ``_reset_git_executor_after_fork``) because a ``ThreadPoolExecutor``
    inherited across a fork has no live worker threads in the child.
    """
    global _git_executor
    if _git_executor is None:
        _git_executor = _DaemonThreadPoolExecutor(
            max_workers=opal_server_config.SCOPES_GIT_MAX_WORKERS,
            thread_name_prefix="opal-git",
        )
    return _git_executor


def shutdown_git_executor() -> None:
    """Drop the dedicated git pool and clear in-flight state.

    Called at the end of the pre-fork ``preload_scopes`` so the gunicorn master
    does not carry idle git-pool threads (or stale in-flight markers) into the
    forked workers. Workers lazily rebuild their own pool on first use.
    """
    global _git_executor
    executor, _git_executor = _git_executor, None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)
    with _git_busy_lock:
        _git_busy.clear()


def _reset_git_executor_after_fork() -> None:
    """Reset the git pool + in-flight state in a freshly forked child.

    A ``ThreadPoolExecutor`` created in the parent is inherited *broken* by the
    child: its worker threads do not survive ``fork``, yet its bookkeeping makes
    ``_adjust_thread_count`` skip spawning live workers, so every submitted task
    would sit queued forever. Dropping the reference forces the child to build
    its own working pool. The in-flight markers are stale in the child too (no
    thread will ever clear them), so clear them.
    """
    global _git_executor
    _git_executor = None
    with _git_busy_lock:
        _git_busy.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_git_executor_after_fork)


def _mark_git_op_started(key: str) -> None:
    with _git_busy_lock:
        _git_busy.add(key)


def _mark_git_op_done(key: str) -> None:
    with _git_busy_lock:
        _git_busy.discard(key)


def git_op_in_flight(key: str) -> bool:
    """True while a git op for ``key`` is still running on a pool thread.

    Stays True during the "lingering" window after a timeout, until the
    blocking pygit2 call actually returns.
    """
    with _git_busy_lock:
        return key in _git_busy


def _consume_future_result(fut) -> None:
    # A future left running after its awaiter timed out is never awaited again;
    # retrieve its outcome so asyncio doesn't log "exception never retrieved".
    if not fut.cancelled():
        try:
            fut.exception()
        except Exception:
            pass


async def run_in_git_executor(func, *args, timeout: float, busy_key=None, **kwargs):
    """Run a blocking git call on the dedicated pool with a hard timeout.

    Raises the builtin ``TimeoutError`` when the call exceeds ``timeout``
    seconds (``timeout <= 0`` means no limit). NOTE: the timeout unblocks the
    event loop and the awaiting coroutine, but the underlying pygit2 call keeps
    running on its pool thread until the OS network timeout; the dedicated pool
    keeps that lingering thread isolated.

    When ``busy_key`` is given it is marked in-flight for the *entire real
    duration* of the call — including any lingering time after a timeout — and
    cleared only when the blocking call actually returns (on the pool thread).
    Callers use ``git_op_in_flight`` to avoid starting a second git op against
    the same repository while a timed-out one is still running.
    """
    loop = asyncio.get_running_loop()

    def _runner():
        try:
            return func(*args, **kwargs)
        finally:
            if busy_key is not None:
                _mark_git_op_done(busy_key)

    if busy_key is not None:
        _mark_git_op_started(busy_key)
    try:
        fut = loop.run_in_executor(_get_git_executor(), _runner)
    except BaseException:
        if busy_key is not None:
            _mark_git_op_done(busy_key)
        raise

    if not (timeout and timeout > 0):
        return await fut

    # Use asyncio.wait (not wait_for) so a timeout does NOT cancel the future:
    # the pool thread runs to completion and clears busy_key, and a still-queued
    # task isn't silently dropped. The done-callback retrieves the eventual
    # result to avoid an "exception never retrieved" warning.
    fut.add_done_callback(_consume_future_result)
    done, _pending = await asyncio.wait({fut}, timeout=timeout)
    if not done:
        raise TimeoutError(f"git operation exceeded {timeout}s")
    return fut.result()


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
        self._source_id = GitPolicyFetcher.source_id(self._source)
        self._auth_callbacks = GitCallback(self._source)
        self._repo_path = self._base_dir / self._source_id
        self._remote = remote_name
        self._scope_id = scope_id
        logger.debug(
            f"Initializing git fetcher: scope_id={scope_id}, url={source.url}, branch={self._source.branch}, source_id={self._source_id}"
        )

    async def _get_repo_lock(self):
        # Previous file based implementation worked across multiple processes/threads, but wasn't fair (next acquiree is random)
        # This implementation works only within the same process/thread, but is fair (next acquiree is the earliest to enter the lock)
        lock = GitPolicyFetcher.repo_locks[
            self._source_id
        ] = GitPolicyFetcher.repo_locks.get(self._source_id, asyncio.Lock())
        return lock

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
        repo_lock = await self._get_repo_lock()
        async with repo_lock:
            if git_op_in_flight(self._source_id):
                # A previous git op for this repo exceeded its timeout and is
                # still running on a pool thread. pygit2 Repository objects are
                # not thread-safe, so skip this cycle rather than touch the same
                # repo concurrently; the next cycle retries once it finishes.
                logger.warning(
                    "Skipping sync for {url}: a previous git operation is still "
                    "running after its timeout.",
                    url=self._source.url,
                )
                return
            with tracer.trace(
                "git_policy_fetcher.fetch_and_notify_on_changes",
                resource=self._scope_id,
            ):
                if self._discover_repository(self._repo_path):
                    logger.debug("Repo found at {path}", path=self._repo_path)
                    repo = self._get_valid_repo()
                    if repo is not None:
                        should_fetch = await self._should_fetch(
                            repo,
                            hinted_hash=hinted_hash,
                            force_fetch=force_fetch,
                            req_time=req_time,
                        )
                        if should_fetch:
                            logger.debug(
                                f"Fetching remote (force_fetch={force_fetch}): {self._remote} ({self._source.url})"
                            )
                            started = datetime.datetime.now()
                            try:
                                await run_in_git_executor(
                                    repo.remotes[self._remote].fetch,
                                    callbacks=self._auth_callbacks,
                                    timeout=opal_server_config.SCOPES_GIT_FETCH_TIMEOUT,
                                    busy_key=self._source_id,
                                )
                            except TimeoutError as exc:
                                # Expected when a repo is unreachable: log cleanly
                                # (no traceback) and skip, matching the clone path.
                                # repos_last_fetched stays stale so the next cycle
                                # retries and force_fetch is not wrongly suppressed.
                                logger.error(
                                    "Timed out fetching {url}, skipping: {err}",
                                    url=self._source.url,
                                    err=repr(exc),
                                )
                                return
                            # Record the fetch *start* time, but only now that it
                            # has succeeded: a completion timestamp could wrongly
                            # suppress a force_fetch whose req_time falls within an
                            # in-flight fetch (see _was_fetched_after).
                            GitPolicyFetcher.repos_last_fetched[
                                self._source_id
                            ] = started
                            logger.debug(f"Fetch completed: {self._source.url}")

                        # New commits might be present because of a previous fetch made by another scope
                        await self._notify_on_changes(repo)
                        return
                    else:
                        # repo dir exists but invalid -> we must delete the directory
                        logger.warning(
                            "Deleting invalid repo: {path}", path=self._repo_path
                        )
                        # ignore_errors: a partial dir left by an abandoned
                        # (timed-out) clone may still be written to; a failed
                        # delete self-heals via the clone below (or next cycle).
                        shutil.rmtree(self._repo_path, ignore_errors=True)
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
            repo: Repository = await run_in_git_executor(
                clone_repository,
                self._source.url,
                str(self._repo_path),
                callbacks=self._auth_callbacks,
                timeout=opal_server_config.SCOPES_GIT_FETCH_TIMEOUT,
                busy_key=self._source_id,
            )
        except (pygit2.GitError, TimeoutError) as exc:
            logger.error(
                "Could not clone repo at {url}: {err}",
                url=self._source.url,
                err=repr(exc),
            )
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
