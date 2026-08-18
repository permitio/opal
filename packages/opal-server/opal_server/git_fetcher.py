import asyncio
import codecs
import datetime
import hashlib
import inspect
import math
import os
import shutil
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import thread as cf_thread
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Dict, Optional, cast

import aiofiles.os
import pygit2
from ddtrace import tracer
from git import Repo
from opal_common.async_utils import run_sync
from opal_common.git_utils.bundle_maker import BundleMaker
from opal_common.http_utils import redact_url
from opal_common.logger import logger
from opal_common.monitoring import metrics
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


class CloneNotPopulatedError(ValueError):
    """The remote-tracking namespace is EMPTY: no refs/remotes/<remote>/* at
    all, so this clone has not been populated yet.

    Distinct from BranchHeadNotFoundError, which means the namespace has refs
    but not the configured one — a real misconfiguration. This is transient by
    construction: _clone() rmtree's the destination and clones INTO the final
    path, so for the whole duration of a recovery re-clone the dir exists with
    no remote refs.

    Deliberately derived from DISK, not from the in-flight marker: that marker
    is a per-process module global, written only by the leader's sync, while
    GET /scopes/{id}/policy is served by any worker. Keying the 503/409 split
    on it made every NON-leader worker answer 409 "not retryable" throughout a
    recovery — the exact inversion the split exists to prevent, on N-1 of N
    workers. Disk truth is identical on every worker.

    Subclasses ValueError so broad handlers still catch it.

    ``waited_seconds`` is how long a request was held waiting for this clone
    before the error was surfaced, and ``client_disconnected`` says the caller
    hung up while it was held, so the answer about to be shaped goes nowhere.
    Both are declared here with defaults rather than read with a getattr
    default at each handler: a raise path that forgets to set one then shows
    up as an explicit default in one place, instead of being
    indistinguishable from "did not wait" at every reader.
    """

    waited_seconds: float = 0.0
    client_disconnected: bool = False


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
    (the pinned libgit2 enforces no network read timeout, so a black-holed
    remote never unblocks it). Daemon workers let the process exit
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
            # _idle_semaphore is used below and is just as private as the rest.
            # A CPython that drops it would rewrite its own _adjust_thread_count
            # accordingly, so the stdlib fallback would still work — but ours
            # would raise AttributeError out of submit(), failing every scope
            # git op. Guarding it is what routes that case to the fallback.
            # (Not demonstrable by deleting the attribute at runtime: that
            # leaves the stdlib's method still using it, a state CPython can
            # never actually be in.)
            # Every private this method goes on to touch, not just the ones
            # whose absence seemed likely. The argument above for
            # _idle_semaphore applies verbatim to each: a CPython that drops
            # one would rewrite its own _adjust_thread_count accordingly, so
            # the stdlib fallback still works while ours raises AttributeError
            # out of submit() and fails every scope git op.
            or not all(
                hasattr(self, name)
                for name in (
                    "_idle_semaphore",
                    "_initargs",
                    "_max_workers",
                    "_thread_name_prefix",
                    "_threads",
                    "_work_queue",
                )
            )
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
    """Drop loop-bound live-op accounting before fork.

    Only the loop-bound semaphores are cleared (meaningless post-fork).
    _git_busy markers are LEFT in place so reset_caches (next) can skip
    freeing a handle a lingering git op still holds; the forked child
    clears the stale markers in _reset_git_executor_after_fork.
    """
    _live_ops_semaphores.clear()


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


def _emit_git_ops_in_flight(count: int) -> None:
    # Continuous gauge so Datadog can watch the in-flight (incl. timed-out
    # zombie) git-op count rise and fall — not just the one-shot error log at
    # the SCOPES_GIT_MAX_ZOMBIES cap. datadog.statsd is fail-silent and
    # thread-safe, so this is safe to call from the git-op daemon threads even
    # when metrics are unconfigured.
    # Tagged by pid: every worker in the gunicorn pool emits this same series,
    # so untagged it is last-write-wins per flush and reads as one arbitrary
    # worker's count rather than anything about the pod.
    metrics.gauge(
        "opal_server.scopes.git_ops_in_flight",
        count,
        tags={"pid": str(os.getpid())},
    )


def _mark_git_op_started(key: str) -> None:
    with _git_busy_lock:
        _git_busy.add(key)
        count = len(_git_busy)
    _emit_git_ops_in_flight(count)


def _mark_git_op_done(key: str) -> None:
    global _zombie_cap_logged
    with _git_busy_lock:
        _git_busy.discard(key)
        count = len(_git_busy)
        if (
            _zombie_cap_logged
            and len(_git_busy) < opal_server_config.SCOPES_GIT_MAX_ZOMBIES
        ):
            _zombie_cap_logged = False
    _emit_git_ops_in_flight(count)


def git_op_in_flight(key: str) -> bool:
    """True while a git op for ``key`` is still running on a pool thread.

    Stays True during the "lingering" window after a timeout, until the
    blocking pygit2 call actually returns.
    """
    with _git_busy_lock:
        return key in _git_busy


def drain_git_ops(timeout: float) -> bool:
    """Block up to `timeout`s for all in-flight git ops to finish.

    Returns True if drained, False if the timeout elapsed with ops still
    lingering. Lets a clone/fetch that finished at the end of the sync
    pass clear its marker before reset_caches runs; ops still lingering
    (unreachable remote) are left running and protected by
    reset_caches's in-flight guard. timeout<=0 = don't wait.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        with _git_busy_lock:
            if not _git_busy:
                return True
        if time.monotonic() >= deadline:
            with _git_busy_lock:
                return not _git_busy
        time.sleep(0.05)


def git_busy_count() -> int:
    """Number of scope git ops holding a pool thread (incl.

    timed-out zombies).
    """
    with _git_busy_lock:
        return len(_git_busy)


@dataclass
class SourceBackoff:
    """How long a repeatedly-failing source is skipped by the periodic pass.

    ``next_attempt_at`` is a ``time.monotonic()`` reading, not wall clock: the
    schedule must survive an NTP step or a container clock jump, and it is only
    ever compared against another monotonic reading in this process.
    """

    consecutive_failures: int
    next_attempt_at: float
    last_error: str


# The exponent is clamped here rather than left to grow with the failure count.
# `2.0 ** (n-1)` raises OverflowError once the exponent passes ~1023 — from
# inside the except clause that is handling the git failure. With a 10s base,
# 2**64 * 10s is ~5.8e12 years: the clamp changes no reachable outcome, it
# only keeps a very old dead source from raising instead of being skipped.
_MAX_BACKOFF_DOUBLINGS = 64

# Past this delay a source is, for practical purposes, abandoned until an
# explicit refresh/PUT or a process restart — worth one WARNING when crossed.
_BACKOFF_ABANDONED_SECONDS = 24 * 3600.0


def _finite_positive_or_zero(value) -> float:
    """Read a config number as a positive finite float, else 0.0.

    Confi parses the environment at import, so a non-numeric value fails the
    process at startup and never reaches this; what this covers is a value
    assigned to the config object at runtime, plus `nan`/`inf`, which parse
    cleanly, start the process, and are not durations anyone meant to set.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(f) or f <= 0:
        return 0.0
    return f


def _backoff_base_seconds() -> float:
    """SCOPES_GIT_BACKOFF_BASE_SECONDS, validated. 0.0 means "disabled".

    The first delay after a source's first failure; each further
    consecutive failure doubles it. Deliberately short (10s by default):
    a delay shorter than the gap to the next pass simply does not skip
    that pass, so the first few doublings cost one attempt per pass
    exactly as before, and the schedule bites from roughly the fourth
    consecutive failure — minutes, then hours, then days. Duplicates of
    a source in the SAME pass are collapsed regardless of the delay by
    the re-check under lock_source.
    """
    return _finite_positive_or_zero(opal_server_config.SCOPES_GIT_BACKOFF_BASE_SECONDS)


def _backoff_max_seconds() -> float:
    """SCOPES_GIT_BACKOFF_MAX_SECONDS, validated. 0.0 means "no cap".

    Uncapped by default on purpose: a repository that has been unreachable
    for a day is, in all likelihood, dead — check it again in two days, then
    four, and before long "at the next restart or explicit refresh". A cap
    is available for operators who would rather bound the staleness of a
    repository that comes back on its own without anyone touching the scope.
    """
    return _finite_positive_or_zero(opal_server_config.SCOPES_GIT_BACKOFF_MAX_SECONDS)


def _backoff_delay(n: int) -> float:
    """The delay armed after the n-th consecutive failure (n >= 1)."""
    base = _backoff_base_seconds()
    raw = base * 2.0 ** min(n - 1, _MAX_BACKOFF_DOUBLINGS)
    cap = _backoff_max_seconds()
    if cap > 0:
        # A cap below the base would make the feature silently inert (every
        # delay shorter than one pass, nothing ever skipped): the base is the
        # floor, so a low cap means "one pass at a time", never "off".
        raw = min(raw, max(cap, base))
    return raw


def _emit_sources_in_backoff() -> None:
    # Gauge of how many sources the periodic pass is currently
    # skipping — the one number that says "this pod is not syncing N of your
    # repos" without reading logs. Tagged by pid for the same reason as
    # _emit_git_ops_in_flight: every worker emits this series, so untagged it
    # is last-write-wins per flush. Never tagged by scope or source — that
    # would make the cardinality proportional to the customer count.
    # LIVE entries only: an entry whose delay has expired is kept so the
    # consecutive-failure count survives until the next attempt, but the pass
    # is not skipping it any more, and the gauge answers "how many sources is
    # this pod not syncing right now". Emitted on every transition AND once
    # per pass (sync_scopes), because DogStatsD gauges report nothing between
    # sends and the steady state this feature creates has few transitions.
    now = time.monotonic()
    # With the kill switch on nothing is skipped regardless of the entries
    # still recorded, so the gauge must read 0 — otherwise the dashboard says
    # "N sources in backoff" every pass while the feature is off.
    if _backoff_base_seconds() <= 0:
        live = 0
    else:
        live = sum(
            1
            for e in GitPolicyFetcher.source_backoff.values()
            if e.next_attempt_at > now
        )
    metrics.gauge(
        "opal_server.scopes.sources_in_backoff",
        live,
        tags={"pid": str(os.getpid())},
    )


# Public name for callers outside this module (the per-pass emission in
# scopes/service.py); the underscore-prefixed one stays for in-module use.
emit_sources_in_backoff = _emit_sources_in_backoff


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
    running on its own daemon thread. Nothing forces it to stop — the pinned
    libgit2 sets no socket/server read timeout — so against a black-holed remote
    that thread (and this key's in-flight marker) can stay alive for the life of
    the process. ``SCOPES_GIT_MAX_ZOMBIES`` is the real bound on how many such
    threads accumulate.

    When ``busy_key`` is given it is marked in-flight for the *entire real
    duration* of the call — including any lingering time after a timeout — and
    cleared only when the blocking call actually returns (on its own thread).
    Callers use ``git_op_in_flight`` to avoid starting a second git op against
    the same repository while a timed-out one is still running.
    """
    global _zombie_cap_logged
    # Clamped like every sibling knob in this subsystem: unclamped, a negative
    # value is truthy AND `count >= cap` holds with nothing in flight, so the
    # very first git op would be refused and no scope would ever sync. Negative
    # reads as "no cap" (0), matching the intent of anyone typing -1 to disable.
    max_zombies = max(0, opal_server_config.SCOPES_GIT_MAX_ZOMBIES)
    if max_zombies and git_busy_count() >= max_zombies:
        if not _zombie_cap_logged:
            _zombie_cap_logged = True
            logger.error(
                "Refusing new scope git op: {count} in-flight at/over "
                "SCOPES_GIT_MAX_ZOMBIES={cap}; remotes appear stuck.",
                count=git_busy_count(),
                cap=max_zombies,
            )
        # Counted on EVERY refusal, unlike the log above which latches once per
        # episode: the log answers "did we hit the cap", the counter answers
        # "how hard and for how long" — the part an operator needs mid-outage.
        metrics.increment(
            "opal_server.scopes.git_ops_refused", tags={"pid": str(os.getpid())}
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
    # source_id -> how long the periodic pass keeps skipping this source after
    # consecutive clone/fetch failures. Per process and in memory only.
    #
    # Mutated ONLY on the event loop: the awaited outcome of a git op is what
    # counts, so a daemon thread that finally returns long after its awaiter
    # timed out never touches this (that late result is unobserved by
    # construction — see run_in_git_executor). No lock is therefore needed, and
    # the read in fetch_and_notify_on_changes deliberately happens before
    # lock_source so a skipped source costs nothing.
    source_backoff: Dict[str, SourceBackoff] = {}

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

    def _backoff_entry(self) -> Optional[SourceBackoff]:
        """This source's live backoff entry, or None if it may be attempted.

        Returns None while the feature is disabled even when an entry exists:
        an operator who sets SCOPES_GIT_BACKOFF_BASE_SECONDS=0 during an
        incident must get the old behaviour back on the next pass, not have to
        wait out the delays already recorded.
        """
        if _backoff_base_seconds() <= 0:
            return None
        entry = GitPolicyFetcher.source_backoff.get(self._source_id)
        if entry is None or time.monotonic() >= entry.next_attempt_at:
            return None
        return entry

    def _record_source_failure(self, err: BaseException) -> None:
        """Count one failed clone/fetch against this source and re-arm the
        delay.

        Called only for failures that say something about the REMOTE (a
        GitError or a timeout). Backpressure from the global zombie cap is
        deliberately not recorded: at that ceiling every scope is refused,
        healthy ones included, so recording it would put the whole fleet into
        backoff because of one bad repo.
        """
        if _backoff_base_seconds() <= 0:
            return  # kill switch: record nothing, so nothing is ever skipped
        previous = GitPolicyFetcher.source_backoff.get(self._source_id)
        n = (previous.consecutive_failures if previous is not None else 0) + 1
        delay = _backoff_delay(n)
        GitPolicyFetcher.source_backoff[self._source_id] = SourceBackoff(
            consecutive_failures=n,
            next_attempt_at=time.monotonic() + delay,
            last_error=repr(err),
        )
        # WARNING only when something changes for the operator: the source
        # ENTERS backoff, its delay first exceeds a day (from here on it is
        # effectively abandoned until a restart or an explicit refresh), or —
        # if a cap is configured — its delay first reaches the cap. Every other
        # recorded failure is DEBUG: the timer's own attempts already get rarer
        # as the delay grows, but an explicit refresh that keeps failing
        # (policy-sync re-issues them constantly for a broken repo) bypasses
        # the backoff and would otherwise WARN on every call, on top of the
        # ERROR the failing op already logged.
        previous_delay = (
            _backoff_delay(previous.consecutive_failures)
            if previous is not None
            else None
        )
        entering = previous is None
        crossed_abandoned = delay >= _BACKOFF_ABANDONED_SECONDS and (
            previous_delay is None or previous_delay < _BACKOFF_ABANDONED_SECONDS
        )
        cap = _backoff_max_seconds()
        reached_cap = (
            cap > 0
            and delay >= max(cap, _backoff_base_seconds())
            and (
                previous_delay is None
                or previous_delay < max(cap, _backoff_base_seconds())
            )
        )
        log = (
            logger.warning
            if (entering or crossed_abandoned or reached_cap)
            else logger.debug
        )
        log(
            "Backing off {url} for {delay:.0f}s after {n} consecutive "
            "failures: {err}",
            url=redact_url(self._source.url),
            delay=delay,
            n=n,
            err=repr(err),
        )
        _emit_sources_in_backoff()

    def _clear_source_backoff(self) -> None:
        """A git op against this source succeeded — drop its failure
        history."""
        previous = GitPolicyFetcher.source_backoff.pop(self._source_id, None)
        if previous is None:
            return
        logger.info(
            "Source {url} recovered after {n} failures",
            url=redact_url(self._source.url),
            n=previous.consecutive_failures,
        )
        _emit_sources_in_backoff()

    @staticmethod
    def forget_source_backoff(source_id: str) -> None:
        """Drop a source's backoff entry when the source itself goes away.

        Called from the purge paths (delete/repoint), never from ``forget_repo``
        — that one is keyed by clone PATH and is also reached mid-sync from the
        invalid-repo recovery branch, where the source is very much still ours
        and its failure history must survive.
        """
        if GitPolicyFetcher.source_backoff.pop(source_id, None) is not None:
            _emit_sources_in_backoff()

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
        *,
        honor_backoff: bool = False,
    ):
        """Makes sure the repo is already fetched and is up to date.

        - if no repo is found, the repo will be cloned.
        - if the repo is found and it is deemed out-of-date, the configured remote will be fetched.
        - if after a fetch new commits are detected, a callback will be triggered.
        - if the hinted commit hash is provided and is already found in the local clone
        we use this hint to avoid an necessary fetch.

        ``honor_backoff`` says this call is pass-originated (the periodic sync
        and the boot preload) and may be skipped while the source is serving
        out a failure backoff. It defaults to False so every explicit path —
        POST /scopes/{id}/refresh, POST /scopes/refresh, PUT /scopes — attempts
        the source immediately: those are someone asking for this repo, now,
        and the most likely reason they are asking is that they just fixed it.
        """
        # Checked before lock_source on purpose (and again under it, below).
        # A hung source holds that lock for the whole clone, so a check ONLY
        # inside it would make every skipped duplicate queue behind the very
        # operation the skip exists to avoid; and a skipped source must
        # consume no git-executor slot, so it can never be refused by (or
        # contribute to) the SCOPES_GIT_MAX_ZOMBIES cap.
        if honor_backoff:
            entry = self._backoff_entry()
            if entry is not None:
                metrics.increment(
                    "opal_server.scopes.git_op_skipped",
                    tags={"reason": "backoff"},
                )
                # DEBUG, not INFO: this fires once per backed-off source per
                # pass, on every pass, for as long as the repo stays broken.
                logger.debug(
                    "Skipping sync for {url}: in backoff for another {left:.0f}s "
                    "after {n} consecutive failures ({err})",
                    url=redact_url(self._source.url),
                    left=max(0.0, entry.next_attempt_at - time.monotonic()),
                    n=entry.consecutive_failures,
                    err=entry.last_error,
                )
                return
        async with GitPolicyFetcher.lock_source(self._source_id):
            # Re-checked under the lock: N pass-originated syncs of one source
            # that arrive together — phase 2 runs the duplicates concurrently,
            # and phase 1 may have recorded nothing for it (refused at the
            # zombie cap, scope gone, no fetch needed) — all pass the cheap
            # pre-lock check before the first has failed and recorded, then
            # serialise here; without this second look each would perform its
            # own full clone attempt against the dead remote.
            if honor_backoff:
                entry = self._backoff_entry()
                if entry is not None:
                    metrics.increment(
                        "opal_server.scopes.git_op_skipped",
                        tags={"reason": "backoff"},
                    )
                    logger.debug(
                        "Skipping sync for {url}: in backoff for another "
                        "{left:.0f}s after {n} consecutive failures ({err})",
                        url=redact_url(self._source.url),
                        left=max(0.0, entry.next_attempt_at - time.monotonic()),
                        n=entry.consecutive_failures,
                        err=entry.last_error,
                    )
                    return
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
                                metrics.increment(
                                    "opal_server.scopes.git_op_failures",
                                    tags={"op": "fetch", "reason": "timeout"},
                                )
                                self._record_source_failure(exc)
                                logger.error(
                                    "Timed out fetching {url}, skipping: {err}",
                                    url=redact_url(self._source.url),
                                    err=repr(exc),
                                )
                                return
                            except pygit2.GitError as exc:
                                # The fast-fail half of the same problem, on a
                                # source that already has a local copy: revoked
                                # credentials or a deleted remote fail here in
                                # ~1s, every pass, forever. Counted as well as
                                # backed off — git_op_failures previously
                                # covered only the CLONE side of git_error, so
                                # a fleet whose fetches were all failing read
                                # as zero failures on the dashboard.
                                metrics.increment(
                                    "opal_server.scopes.git_op_failures",
                                    tags={"op": "fetch", "reason": "git_error"},
                                )
                                self._record_source_failure(exc)
                                # Re-raised, not swallowed: sync_scope's
                                # per-scope handler logs it with a traceback
                                # today, and that is left exactly as it was.
                                raise
                            GitPolicyFetcher.repos_last_fetched[
                                self._source_id
                            ] = fetch_started
                            self._clear_source_backoff()
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
                # is serialized against any purge on THIS process. Fails open:
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
            metrics.increment(
                "opal_server.scopes.git_op_failures",
                tags={
                    "op": "clone",
                    # The distinction the log line cannot carry: a steady rate of
                    # timeouts against known-unreachable repos is expected after
                    # SCOPES_GIT_FETCH_TIMEOUT landed; a git_error is not.
                    "reason": "timeout"
                    if isinstance(exc, TimeoutError)
                    else "git_error",
                },
            )
            self._record_source_failure(exc)
            logger.error(
                "Could not clone repo at {url}: {err}",
                url=redact_url(self._source.url),
                err=repr(exc),
            )
        else:
            logger.info(f"Clone completed: {redact_url(self._source.url)}")
            # Cleared on the awaited SUCCESS of the git op itself, before the
            # local bookkeeping below: the remote is demonstrably reachable, so
            # a later failure inside _notify_on_changes (a corrupt object
            # store, say) must not leave the source marked as unreachable.
            self._clear_source_backoff()
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
            # Resolve the branch ref inline rather than via
            # RepoInterface.get_commit_hash, which collapses BOTH failure modes
            # to None. On the serving path we must tell them apart:
            #   * KeyError  -> the branch ref genuinely does not exist: a
            #     PERMANENT misconfiguration (wrong/deleted branch). Surface it
            #     as BranchHeadNotFoundError -> the bundle route's 409
            #     "not retryable".
            #   * pygit2.GitError -> the ref is present but its object can't be
            #     resolved right now (object store transiently gutted by a
            #     concurrent re-clone/fetch). This is TRANSIENT and the sync
            #     path is already self-healing it, so let it propagate: the
            #     bundle route's own pygit2.GitError handler turns it into a
            #     retryable 503, instead of telling the client "not retryable"
            #     for a scope that will recover on its own.
            try:
                commit, _ = repo.resolve_refish(f"{self._remote}/{self._source.branch}")
                head_commit_hash = commit.hex
            except KeyError:
                # Split the KeyError by DISK STATE, not by the in-flight marker:
                # an empty remote-tracking namespace means the clone has not been
                # populated yet (transient), whereas siblings present but ours
                # missing means the configured branch is wrong (permanent).
                prefix = f"refs/remotes/{self._remote}/"
                if not any(ref.startswith(prefix) for ref in repo.listall_references()):
                    raise CloneNotPopulatedError(
                        f"No {prefix}* refs yet at {self._repo_path}"
                    )
                head_commit_hash = None
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

        A source whose git op is still in flight (lingering past its
        timeout on a daemon thread) is skipped: its handle is only
        dropped from the cache, never free()'d, since the pool thread
        may still be reading from it — free()'ing it here would be a
        use-after-free. GC reclaims it once the blocking call actually
        returns.

        ``source_backoff`` is deliberately NOT cleared. It holds no handles,
        no fds and no loop-bound objects, so none of the reasons above apply —
        and the preload this runs after is exactly where a dead repo's clone
        failures are discovered. Letting the forked leader inherit them is
        the point when a periodic pass follows: otherwise the leader starts
        by re-hammering the same unreachable repos, which is the boot storm the
        backoff exists to collapse. (When no periodic pass follows,
        ScopesPolicyWatcherTask.start() drops the inherited entries itself, so
        the one boot sync still attempts every source once.)
        ``_reset_git_executor_after_fork`` leaves it alone for the same
        reason.
        """
        for path in list(GitPolicyFetcher.repos):
            source_id = os.path.basename(path.rstrip("/"))
            if git_op_in_flight(source_id):
                # Still in use on a pool thread — drop the reference, never free
                # (free()'ing a handle a daemon thread holds is a use-after-free).
                # GC reclaims it once the blocking call returns. Mirrors
                # purge_local_memory's guard.
                GitPolicyFetcher.repos.pop(path, None)
                continue
            GitPolicyFetcher.forget_repo(path)
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
