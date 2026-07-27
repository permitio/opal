import asyncio
import codecs
import datetime
import hashlib
import inspect
import os
import shutil
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import thread as cf_thread
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Awaitable, Callable, Optional, cast

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

# Source ids whose scope git op (clone/fetch) is still running on a pool thread
# — including one that already exceeded its timeout but whose blocking pygit2
# call has not yet returned. Guarded by a lock because it is cleared from the
# pool thread (see ``run_in_git_executor``) and read/written from the event
# loop. Used to guarantee at most one live git op per repository, since pygit2
# ``Repository`` objects are not thread-safe.
_git_busy: set = set()
_git_busy_lock = threading.Lock()


class GitConcurrencyLimitExceeded(RuntimeError):
    """Raised when in-flight (live + zombie) git ops reach
    SCOPES_GIT_MAX_ZOMBIES."""


class BranchHeadNotFoundError(ValueError):
    """Configured branch has no resolvable HEAD (permanent misconfig), NOT a
    transient clone gap.

    Subclasses ValueError so broad handlers still catch it.
    """


_zombie_cap_logged = False


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
        worker = getattr(cf_thread, "_worker", None)
        # Fall back to the stdlib if any internal we mirror has moved or changed
        # shape: _worker must exist and take exactly the 4 positional args we pass,
        # _threads_queues must exist, and this executor must expose _initializer.
        if (
            worker is None
            or not hasattr(cf_thread, "_threads_queues")
            or not hasattr(self, "_initializer")
        ):
            return super()._adjust_thread_count()
        try:
            if len(inspect.signature(worker).parameters) != 4:
                return super()._adjust_thread_count()
        except (TypeError, ValueError):
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
            # Deliberately NOT registered in ``cf_thread._threads_queues``:
            # the stdlib's ``_python_exit`` atexit handler iterates that global
            # and ``join()``s every thread in it regardless of ``daemon=True``,
            # which would block interpreter shutdown on a lingering (timed-out)
            # git call — the exact "stuck on an offline repo" hang this class
            # exists to avoid, relocated to shutdown/restart. Normal shutdown
            # uses ``self._threads`` + queue sentinels and is unaffected.


def shutdown_git_executor() -> None:
    """Clear in-flight markers and live-op accounting.

    Called at the end of the pre-fork ``preload_scopes`` so the gunicorn
    master does not carry stale in-flight markers (or loop-bound semaphores)
    into forked workers. Per-op executors need no teardown: their daemon
    threads die with their ops (or the process).
    """
    _live_ops_semaphores.clear()
    with _git_busy_lock:
        _git_busy.clear()


def _reset_git_executor_after_fork() -> None:
    """after_in_child fork handler: _git_busy_lock is held on entry (the paired
    'before' handler acquired it and the child inherits it LOCKED). Reinit it in
    place FIRST (dropping it without a matching acquire — re-acquiring would
    deadlock), then mutate _git_busy directly (child is single-threaded here)."""
    global _git_busy_lock
    reinit = getattr(_git_busy_lock, "_at_fork_reinit", None)
    if callable(reinit):
        reinit()
    else:  # pragma: no cover
        _git_busy_lock = threading.Lock()
    _live_ops_semaphores.clear()
    _git_busy.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        before=_git_busy_lock.acquire,
        after_in_parent=_git_busy_lock.release,
        after_in_child=_reset_git_executor_after_fork,
    )


def _mark_git_op_started(key: str) -> None:
    with _git_busy_lock:
        _git_busy.add(key)


def _mark_git_op_done(key: str) -> None:
    global _zombie_cap_logged
    with _git_busy_lock:
        _git_busy.discard(key)
        if (
            _zombie_cap_logged
            and len(_git_busy) < opal_server_config.SCOPES_GIT_MAX_ZOMBIES
        ):
            _zombie_cap_logged = False


def git_op_in_flight(key: str) -> bool:
    """True while a git op for ``key`` is still running on a pool thread.

    Stays True during the "lingering" window after a timeout, until the
    blocking pygit2 call actually returns.
    """
    with _git_busy_lock:
        return key in _git_busy


def git_busy_count() -> int:
    """Number of scope git ops holding a pool thread (incl.

    timed-out zombies).
    """
    with _git_busy_lock:
        return len(_git_busy)


def _consume_future_result(fut) -> None:
    # A future left running after its awaiter timed out is never awaited again;
    # retrieve its outcome so asyncio doesn't log "exception never retrieved".
    if not fut.cancelled():
        try:
            fut.exception()
        except Exception:
            pass


# Bounds LIVE (non-timed-out) git ops. asyncio primitives are loop-bound, so
# the semaphore is minted per running loop (WeakKeyDictionary: a dead loop's
# entry vanishes with it). A timed-out op releases its slot while its zombie
# thread lingers — capacity is never consumed by zombies (a fixed pool
# starves once zombies exceed its size; see the offline-repo bed gate).
_live_ops_semaphores: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _get_live_ops_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _live_ops_semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(max(1, opal_server_config.SCOPES_GIT_MAX_WORKERS))
        _live_ops_semaphores[loop] = sem
    return sem


async def run_in_git_executor(func, *args, timeout: float, busy_key=None, **kwargs):
    """Run a blocking git call on its own daemon thread with a hard timeout.

    ``SCOPES_GIT_MAX_WORKERS`` bounds LIVE (non-timed-out) ops via an asyncio
    semaphore; each op still gets its own single-use daemon-thread executor,
    so a lingering ("zombie") op after a timeout never occupies a shared pool
    slot — it keeps running on its private thread but no longer counts
    against the concurrency bound.

    Raises the builtin ``TimeoutError`` when the call exceeds ``timeout``
    seconds (``timeout <= 0`` means no limit). NOTE: the timeout unblocks the
    event loop and the awaiting coroutine, but the underlying pygit2 call keeps
    running on its own daemon thread until the OS network timeout.

    When ``busy_key`` is given it is marked in-flight for the *entire real
    duration* of the call — including any lingering time after a timeout — and
    cleared only when the blocking call actually returns (on its own thread).
    Callers use ``git_op_in_flight`` to avoid starting a second git op against
    the same repository while a timed-out one is still running.
    """
    global _zombie_cap_logged
    max_zombies = opal_server_config.SCOPES_GIT_MAX_ZOMBIES
    if max_zombies and git_busy_count() >= max_zombies:
        if not _zombie_cap_logged:
            _zombie_cap_logged = True
            logger.error(
                "Refusing new scope git op: {count} in-flight at/over "
                "SCOPES_GIT_MAX_ZOMBIES={cap}; remotes appear stuck.",
                count=git_busy_count(),
                cap=max_zombies,
            )
        raise GitConcurrencyLimitExceeded(
            f"in-flight git ops ({git_busy_count()}) reached "
            f"SCOPES_GIT_MAX_ZOMBIES ({max_zombies})"
        )

    loop = asyncio.get_running_loop()

    def _runner():
        try:
            return func(*args, **kwargs)
        finally:
            if busy_key is not None:
                _mark_git_op_done(busy_key)

    sem = _get_live_ops_semaphore()
    await sem.acquire()
    released = False

    def _release_once():
        nonlocal released
        if not released:
            released = True
            sem.release()

    try:
        # Single-use executor: the op gets a private daemon thread, so a zombie
        # never blocks the next op the way a fixed shared pool does. shutdown
        # with wait=False just drops bookkeeping; the daemon thread dies with
        # the pygit2 call (or the process).
        executor = _DaemonThreadPoolExecutor(
            max_workers=1, thread_name_prefix="opal-git"
        )
        if busy_key is not None:
            _mark_git_op_started(busy_key)
        try:
            fut = loop.run_in_executor(executor, _runner)
        except BaseException:
            if busy_key is not None:
                _mark_git_op_done(busy_key)
            executor.shutdown(wait=False)
            raise
        fut.add_done_callback(lambda f: executor.shutdown(wait=False))

        if not (timeout and timeout > 0):
            return await fut

        # asyncio.wait (not wait_for) so a timeout does NOT cancel the future:
        # the thread runs to completion and clears busy_key; the done-callback
        # retrieves the eventual result to avoid "exception never retrieved".
        fut.add_done_callback(_consume_future_result)
        done, _pending = await asyncio.wait({fut}, timeout=timeout)
        if not done:
            # Zombie: free the capacity slot; the private daemon thread lingers
            # until the OS gives up, tracked only by busy_key.
            raise TimeoutError(f"git operation exceeded {timeout}s")
        return fut.result()
    finally:
        _release_once()


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
        liveness_probe: Optional[Callable[[], Awaitable[bool]]] = None,
    ):
        super().__init__(callbacks)
        self._base_dir = GitPolicyFetcher.base_dir(base_dir)
        self._source = source
        self._source_id = GitPolicyFetcher.source_id(self._source)
        self._auth_callbacks = GitCallback(self._source)
        self._repo_path = self._base_dir / self._source_id
        self._remote = remote_name
        self._scope_id = scope_id
        self._liveness_probe = liveness_probe
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
            if git_op_in_flight(self._source_id):
                # A previous git op for this repo exceeded its timeout and is
                # still running on a pool thread. pygit2 Repository objects are
                # not thread-safe, so skip this cycle rather than touch the same
                # repo concurrently; the next cycle retries once it finishes.
                logger.warning(
                    "Skipping sync for {url}: a previous git operation is still "
                    "running after its timeout.",
                    url=redact_url(self._source.url),
                )
                return
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
                                    url=redact_url(self._source.url),
                                    err=repr(exc),
                                )
                                return
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
                            # A partial dir left by an abandoned (timed-out)
                            # clone may still be written to; a failed delete
                            # self-heals via the clone below (or next cycle).
                            logger.warning(
                                f"Failed to remove clone dir "
                                f"{self._repo_path}: {e!r}"
                            )
                else:
                    logger.info("Repo not found at {path}", path=self._repo_path)

                # fallthrough to clean clone
                # Liveness check before clone (the resurrection point): a
                # DELETE that landed during this sync already broadcast its
                # purge; cloning now would resurrect the dead scope's repo
                # and re-populate the caches. Runs under lock_source, so it
                # is serialized against the leader's disk purge. Fails open:
                # a store hiccup must not block the sync.
                if self._liveness_probe is not None:
                    try:
                        alive = await self._liveness_probe()
                    except Exception as e:
                        logger.warning(
                            "Liveness probe for scope {scope} failed, "
                            "proceeding with clone: {err}",
                            scope=self._scope_id,
                            err=repr(e),
                        )
                        alive = True
                    if not alive:
                        logger.info(
                            "Scope {scope} was deleted mid-sync, skipping clone",
                            scope=self._scope_id,
                        )
                        return
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
                url=redact_url(self._source.url),
                err=repr(exc),
            )
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
            raise BranchHeadNotFoundError("Could not find current branch head")
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

    @staticmethod
    def reset_caches() -> None:
        """Free and drop every cached repo handle, lock, and timestamp.

        Called in the gunicorn master after preload and before fork so
        no fetcher state is inherited by workers. A forked worker that
        inherited a handle for a scope it never syncs (sync is leader-
        only) could never purge it — the fleet-wide purge broadcast only
        reaches workers whose broadcaster reader is running — so it
        would pin that handle for life. Workers re-open handles lazily
        from the on-disk clones (preserved). Inherited repo_locks are
        asyncio.Locks bound to the master's event loop and meaningless
        post-fork regardless.
        """
        for path in list(GitPolicyFetcher.repos):
            GitPolicyFetcher.forget_repo(path)  # frees the pygit2 handle + pops
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.repo_locks.clear()


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
