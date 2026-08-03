"""Fleet-wide purge of GitPolicyFetcher caches (PR3 of the leak series).

Every worker subscribes ``handle_purge_message`` to SCOPES_PURGE_CHANNEL at
startup (see ``server.py``) and drops its in-memory cache entries for the
purged source. The leader additionally registers ``LeaderScopePurger.handle``
(at watcher start) which removes the clone dir — only the leader mutates the
clone tree.
"""
import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from opal_common.async_utils import run_sync
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, git_op_in_flight
from pydantic import BaseModel, ValidationError

# \Z (not $) so a trailing newline can't sneak past validation: in Python `$`
# also matches just before a final "\n", so "<64hex>-0\n" would wrongly pass.
_SOURCE_ID_RE = re.compile(r"\A[0-9a-f]{64}-\d+\Z")

# Event-loop yield cadence for the orphan sweep's candidate loop. Purely about
# not starving the loop on a very large clone tree — deliberately NOT also the
# freshness cadence of the store read: the deletion decision takes its own read
# under the candidate's lock (see LeaderScopePurger._classify_candidate), so
# raising this can never widen a staleness window.
_YIELD_EVERY = 200

# How many consecutive passes a dir must look orphaned before it may be
# reclaimed. A store that is briefly wrong — a replica seconds behind after a
# failover, an LRU eviction of Scope keys, a partial restore — answers correctly
# again by the next pass, so its records reappear and the dir never becomes
# eligible. Only a dir that is *persistently* unreferenced is deleted, which is
# the actual definition of an orphan.
_REQUIRED_ORPHAN_STREAK = 2

# One-shot latch so an explicitly-disabled reclaim cap is reported once, not on
# every sweep pass (mirrors git_fetcher's _zombie_cap_logged).
_reclaim_cap_disabled_warned = False


def _confined_clone_path(base_dir, source_id: str):
    """Derive the on-disk clone dir for ``source_id``, or ``None`` if the id is
    malformed.

    SECURITY: a purge command's ``clone_path`` field arrives over pub/sub and
    must NEVER reach the filesystem — a forged message could otherwise carry
    an arbitrary path into ``rmtree``/``free()``. ``source_id`` is a sha256
    hex digest + shard index (no separators, no traversal), so the derived
    path is always confined to ``base_dir/git_sources``. The result is also
    the exact key used in ``GitPolicyFetcher.repos``.
    """
    if not _SOURCE_ID_RE.match(source_id):
        return None
    return str(GitPolicyFetcher.base_dir(Path(base_dir)) / source_id)


class ScopePurgeCommand(BaseModel):
    source_id: str  # cache key for repos_last_fetched / repo_locks
    # Informational only: every handler re-derives the clone dir from source_id
    # (never trusts this path); kept for readable logs and forward-compat.
    clone_path: str
    scope_id: str  # logging / tracing only
    # Load-bearing, NOT just logging: the leader's sibling-check fail-open
    # branches on reason (repoint keeps the clone on a raising scan; delete/
    # orphan purge). See LeaderScopePurger.purge_source_if_unshared.
    reason: str  # "delete" | "repoint" | "orphan"
    confirmed: bool = False  # set by the leader after the sibling-check;
    # memory handlers act only on confirmed commands


def purge_local_memory(source_id: str, clone_path: str) -> None:
    """Drop this process's in-memory cache entries for a source.

    Never pops ``repo_locks``: lock_source's recheck loop protects waiters,
    not a current holder — popping is only safe while holding the lock (the
    leader's disk purge does it there). ``forget_repo`` is skipped while a
    git op is in flight: freeing a pygit2 handle a pool thread still uses
    (e.g. a lingering timed-out fetch) is a crash risk; a skipped free
    self-heals via the orphan sweep or the next validity probe.
    """
    if not git_op_in_flight(source_id):
        GitPolicyFetcher.forget_repo(clone_path)
    GitPolicyFetcher.repos_last_fetched.pop(source_id, None)


async def handle_purge_message(subscription, data: Any) -> None:
    """Every-worker subscriber for SCOPES_PURGE_CHANNEL."""
    try:
        cmd = ScopePurgeCommand(**data)
    except (ValidationError, TypeError):
        logger.warning("Ignoring malformed scope purge message: {data}", data=data)
        return
    if not cmd.confirmed:
        # A request — only the leader acts on those (sibling-check first).
        return
    safe_path = _confined_clone_path(opal_server_config.BASE_DIR, cmd.source_id)
    if safe_path is None:
        logger.warning(
            "Ignoring scope purge with malformed source_id: {sid}",
            sid=cmd.source_id,
        )
        return
    logger.info(
        "Purging local caches for source {source_id} (scope {scope_id}, {reason})",
        source_id=cmd.source_id,
        scope_id=cmd.scope_id,
        reason=cmd.reason,
    )
    # Under lock_source — a FRESH lock, not the one the leader holds while it
    # publishes the confirmation: the leader pops the repo_locks entry before
    # publishing precisely so this handler's setdefault mints a new one instead
    # of deadlocking on the held one (see purge_source_if_unshared).
    # forget_repo -> Repository.free() must not run concurrently with a
    # re-created scope's sync on THIS process: fetch_and_notify_on_changes holds
    # its handle across an await and then set_target()s it, all under
    # lock_source. The git_op_in_flight guard inside purge_local_memory only
    # covers pool-thread ops, not that event-loop handle-holding — so without
    # the lock this every-worker handler is the use-after-free the leader path
    # is careful to avoid, on every process except the publisher.
    async with GitPolicyFetcher.lock_source(cmd.source_id):
        purge_local_memory(cmd.source_id, safe_path)
        # Pop the repo_locks entry lock_source just minted (via setdefault),
        # under the lock — the same lock-identity rule the leader follows in
        # purge_source_if_unshared. purge_local_memory deliberately never pops it
        # (it held no lock); now that this handler does, popping here is what
        # keeps a purged source from leaving a stray repo_locks key (invariant
        # I4). lock_source waiters re-check the dict and re-mint a fresh lock, so
        # a concurrently re-created scope is unaffected.
        GitPolicyFetcher.repo_locks.pop(cmd.source_id, None)


async def subscribe_worker_purge_handler(endpoint) -> None:
    await endpoint.subscribe(
        [opal_server_config.SCOPES_PURGE_CHANNEL], handle_purge_message
    )


def _scope_sharing_source(
    scopes_snapshot, source_id: str, excluded_scope_id: Optional[str] = None
) -> Optional[str]:
    """First live scope in a pre-fetched list mapping to ``source_id``, else
    None.

    Pure (no I/O): RAISES if a scope's ``source_id()`` derivation raises —
    the caller owns the fail-open/fail-closed policy for that. Reused by
    the orphan sweep (C4.5).
    """
    return next(
        (
            s.scope_id
            for s in scopes_snapshot
            if s.scope_id != excluded_scope_id
            and isinstance(s.policy, GitPolicyScopeSource)
            and GitPolicyFetcher.source_id(s.policy) == source_id
        ),
        None,
    )


async def find_scope_sharing_source(
    scopes, source_id: str, excluded_scope_id: Optional[str] = None
) -> Optional[str]:
    """Return the id of a live scope mapping to ``source_id``, or None.

    RAISES on a store/scan error (was: swallowed and returned None). The
    caller decides the fail-open policy by ``reason``: a repoint's old
    source still has a live record (just moved elsewhere), so a raising
    scan must NOT read as "unshared"; a delete's record is already gone,
    so under-purging there is a permanent leak.
    """
    return _scope_sharing_source(await scopes.all(), source_id, excluded_scope_id)


def _list_dir_names(path: str) -> list:
    """Immediate subdirectory names (dirs only) of ``path``.

    Uses ``os.scandir`` so the ``is_dir()`` stat comes from the (cached)
    ``DirEntry`` rather than a second syscall per entry, and — via
    ``run_sync`` at the call site — runs on a worker thread, not the event
    loop.
    """
    with os.scandir(path) as it:
        return [entry.name for entry in it if entry.is_dir()]


class LeaderScopePurger:
    """Leader-only: removes clone dirs for purged sources.

    Registered on SCOPES_PURGE_CHANNEL when leadership is acquired (the
    watcher task's start), preserving the invariant that only the leader
    mutates the clone tree.
    """

    def __init__(self, base_dir: Path, scopes, pubsub_endpoint):
        self._base_dir = base_dir
        self._scopes = scopes
        self._pubsub_endpoint = pubsub_endpoint
        # Strong refs to in-flight background purges (create_task results are
        # otherwise GC-able); discarded on completion.
        self._pending_purges = set()
        # Set by signal_stop(): no new purge is queued once shutdown started.
        self._stopping = False
        # dir name -> consecutive passes it has looked orphaned. Pruned to the
        # current candidate set each pass (see _eligible_for_reclaim), so it
        # cannot grow without bound and a dir that stops looking orphaned starts
        # over. Leader-local: a leadership change costs one extra pass of delay.
        self._orphan_streak = {}

    async def _purge_and_log(self, cmd: ScopePurgeCommand) -> None:
        try:
            await self.purge_source_if_unshared(cmd)
        except Exception:
            # Detached background task: without this, an unexpected failure
            # (e.g. the confirmation publish hitting a broadcaster error)
            # surfaces only as asyncio's unretrieved-exception noise.
            logger.exception(
                f"Background purge of source {cmd.source_id} " f"({cmd.reason}) failed"
            )

    async def handle(self, subscription, data: Any):
        try:
            cmd = ScopePurgeCommand(**data)
        except (ValidationError, TypeError):
            # The worker-level handler already logged the malformed payload.
            return None
        if cmd.confirmed:
            return None  # our own confirmation broadcast, addressed to workers
        if self._stopping:
            # Shutdown started: the watcher has already unsubscribed us and is
            # about to drain what is in flight. Queuing more work here would
            # either be abandoned by that bounded drain or start an rmtree
            # nothing waits on. The next leader's boot sweep reclaims it —
            # unless the store reads empty by then (the last scope's dir), which
            # that sweep refuses to act on by default (see
            # SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE).
            logger.info(
                f"Ignoring purge request for {cmd.source_id} ({cmd.reason}): "
                "purger is stopping"
            )
            return None
        # publish() awaits subscriber callbacks inline — never do lock-waiting
        # disk work on the publisher's request path (DELETE/PUT latency is
        # bounded by contract). The purge proceeds in the background.
        task = asyncio.create_task(self._purge_and_log(cmd))
        self._pending_purges.add(task)
        task.add_done_callback(self._pending_purges.discard)
        return task

    def signal_stop(self) -> None:
        """Refuse new purge requests from ``handle`` (idempotent)."""
        self._stopping = True

    async def stop(self) -> None:
        """Await in-flight background purges so a shutdown can't abandon an
        rmtree mid-flight (or run a fresh one after the watcher stopped).

        These tasks are spawned detached in ``handle`` and are NOT in the
        watcher's ``self._tasks``, so ``BasePolicyWatcherTask.stop`` never waits
        on them.

        This CAN block for a long time and the caller must bound it: a purge's
        first act is to take ``lock_source``, held by a sync across a whole
        clone/fetch (unbounded when ``SCOPES_GIT_FETCH_TIMEOUT`` is 0), and it
        then does a ``scopes.all()`` and a confirmation ``publish()`` against a
        Redis/broadcaster client with no socket timeout. The watcher calls this
        after cancelling its tasks (so the lock holders are gone) and under an
        ``asyncio.wait_for``.
        """
        self.signal_stop()
        if self._pending_purges:
            await asyncio.gather(*list(self._pending_purges), return_exceptions=True)

    async def purge_source_if_unshared(self, cmd: ScopePurgeCommand) -> None:
        safe_path = _confined_clone_path(self._base_dir, cmd.source_id)
        if safe_path is None:
            logger.warning(
                f"Ignoring leader purge with malformed source_id: {cmd.source_id}"
            )
            return
        confirm = False
        async with GitPolicyFetcher.lock_source(cmd.source_id):
            try:
                timeout = opal_server_config.SCOPES_ORPHAN_SWEEP_STORE_READ_TIMEOUT
                check = find_scope_sharing_source(self._scopes, cmd.source_id)
                sharer = await (
                    asyncio.wait_for(check, timeout=timeout) if timeout > 0 else check
                )
            except asyncio.TimeoutError:
                # Same bound, same fail-safe direction as the sweep's re-check:
                # this read is held under lock_source too, and the Redis client
                # has no socket timeout, so an unreachable store would otherwise
                # wedge this source's lock for the life of the process — every
                # later sync, purge and sweep for it included. Keeping the clone
                # is the conservative outcome; the orphan sweep backstops it.
                logger.warning(
                    "Sibling check for {sid} timed out after {t}s; keeping the "
                    "clone (the orphan sweep backstops it)",
                    sid=cmd.source_id,
                    t=opal_server_config.SCOPES_ORPHAN_SWEEP_STORE_READ_TIMEOUT,
                )
                return
            except Exception as e:
                if cmd.reason == "repoint":
                    # The old source's record wasn't deleted — it was just
                    # repointed elsewhere — so a raising scan can't be told
                    # apart from "still shared". Keep the clone; the orphan
                    # sweep backstops it once the scan recovers.
                    logger.warning(
                        f"Sibling check for {cmd.source_id} failed on repoint; "
                        f"keeping the clone (orphan sweep backstops): {e!r}"
                    )
                    return
                logger.warning(
                    f"Sibling check for {cmd.source_id} failed on {cmd.reason}; "
                    f"purging defensively: {e!r}"
                )
                sharer = None
            if sharer is not None:
                logger.info(
                    f"Scope {sharer} still shares source {cmd.source_id}, "
                    "keeping the clone"
                )
            elif git_op_in_flight(cmd.source_id):
                # A lingering (timed-out) git op still touches the repo on a
                # pool thread: freeing the pygit2 handle or deleting the dir
                # now risks a crash, so those wait for the orphan sweep. The
                # lock and timestamp entries are event-loop-side objects the
                # thread never touches — drain them now (under the held lock,
                # per the lock-identity rule) and confirm, so workers drop
                # their memory entries; the leader's own handle survives via
                # purge_local_memory's in-flight guard.
                logger.warning(
                    f"Deferring clone-dir removal for {cmd.source_id}: a git "
                    "operation is still in flight (orphan sweep reclaims it); "
                    "draining lock/timestamp entries now"
                )
                GitPolicyFetcher.repos_last_fetched.pop(cmd.source_id, None)
                GitPolicyFetcher.repo_locks.pop(cmd.source_id, None)
                confirm = True
            else:
                GitPolicyFetcher.forget_repo(safe_path)
                GitPolicyFetcher.repos_last_fetched.pop(cmd.source_id, None)
                try:
                    await run_sync(shutil.rmtree, safe_path)
                except FileNotFoundError:
                    pass  # already gone — the intended end state
                except OSError as e:
                    logger.warning(f"Failed to remove clone dir {safe_path}: {e!r}")
                # Popped while the lock is held: lock_source waiters re-check
                # the dict entry after acquiring and retry on the fresh lock.
                #
                # LOAD-BEARING ORDER: this pop must stay BEFORE the confirmation
                # publish below, not moved after it as a "clean up last" tidy-up.
                # publish() runs local subscribers inline on this very task, and
                # handle_purge_message re-enters lock_source(source_id) — the
                # same non-reentrant asyncio.Lock still held here. Popping first
                # makes that handler's setdefault mint a FRESH lock instead of
                # waiting on ours; popping after would wedge lock_source for this
                # source permanently, hanging every later sync, purge and sweep
                # for it (and, via the watcher's stop(), shutdown too).
                GitPolicyFetcher.repo_locks.pop(cmd.source_id, None)
                confirm = True
            # Published under the lock, like sweep_orphans: publish() runs
            # local subscribers inline, so the confirmation frees this
            # process's cached pygit2 handle. Releasing the lock first would
            # let a re-created scope's sync acquire it, cache a fresh handle,
            # and enter _notify_on_changes — which holds the handle across an
            # await and then calls set_target() on it — while this stale
            # confirmation frees it underneath (use-after-free).
            if confirm and self._pubsub_endpoint is not None:
                await self._pubsub_endpoint.publish(
                    [opal_server_config.SCOPES_PURGE_CHANNEL],
                    cmd.copy(update={"confirmed": True}).dict(),
                )

    async def _classify_candidate(self, source_id: str, dir_names) -> str:
        """Decide one candidate's fate from a FRESH read taken under its lock.

        Returns ``"orphan"`` (safe to reclaim), ``"claimed"`` (keep this dir) or
        ``"abort"`` (stop the whole pass).

        The read MUST happen here, inside ``lock_source(source_id)``, not once
        for a batch of candidates: holding the lock excludes a concurrent
        clone/fetch for this source (cloning is leader-local and takes the same
        lock), but it cannot make an older read fresh. A batched read is only a
        pre-filter — by the time the loop reaches the Nth candidate it predates
        N-1 lock acquisitions and rmtrees, so a PUT that re-claimed this source
        in that window would be invisible and a LIVE tenant's clone would be
        deleted (plus a confirmed orphan purge broadcast fleet-wide). That is
        not self-healing at the shipped defaults: POLICY_REFRESH_INTERVAL is 0,
        so nothing re-clones and the scope serves 503 until a webhook or a
        manual refresh-all arrives.

        The cost is a full SCAN per candidate, but only for dirs that already
        look orphaned AND survived the plausibility ceiling — the common
        all-live pass reaches this zero times, and ``_reclaim_is_plausible``
        caps how many candidates can ever get here in one pass.
        """
        timeout = opal_server_config.SCOPES_ORPHAN_SWEEP_STORE_READ_TIMEOUT
        try:
            read = self._scopes.all()
            fresh = await (
                asyncio.wait_for(read, timeout=timeout) if timeout > 0 else read
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Orphan re-check for {sid} timed out after {t}s, keeping dir. The "
                "read is a SCAN plus a GET per key, so a large store may need a "
                "higher SCOPES_ORPHAN_SWEEP_STORE_READ_TIMEOUT — until then this "
                "source can never be reclaimed.",
                sid=source_id,
                t=timeout,
            )
            metrics.event(
                "ScopeOrphanSweepRefused",
                message=f"Orphan sweep: store read timed out after {timeout}s",
                tags={"reason": "store_read_timeout"},
            )
            return "undecided"
        except Exception as e:
            logger.warning(
                f"Orphan re-check for {source_id} failed, keeping dir: {e!r}"
            )
            metrics.event(
                "ScopeOrphanSweepRefused",
                message="Orphan sweep: store read failed during the under-lock re-check",
                tags={"reason": "recheck_failed", "error": type(e).__name__},
            )
            return "undecided"
        if not self._may_reclaim(fresh, dir_names):
            # The store emptied out mid-pass: same refusal as the pass-level
            # guard, and it applies to every remaining candidate too.
            return "abort"
        # Derive per scope, exactly as the snapshot loop does: _scope_sharing_source
        # is a next() over ALL scopes and a candidate never matches, so it always
        # walks the whole list — one malformed record would otherwise raise for
        # EVERY candidate on EVERY pass and silently switch the backstop off.
        unresolvable = 0
        for scope in fresh:
            if not isinstance(scope.policy, GitPolicyScopeSource):
                continue
            try:
                if GitPolicyFetcher.source_id(scope.policy) == source_id:
                    return "claimed"  # re-claimed since the snapshot
            except Exception as e:
                unresolvable += 1
                logger.warning(
                    "Orphan re-check for {sid}: scope {scope_id}'s source_id will "
                    "not derive, so this dir cannot be proven unreferenced: {err}",
                    sid=source_id,
                    scope_id=scope.scope_id,
                    err=repr(e),
                )
        if unresolvable:
            metrics.event(
                "ScopeOrphanSweepRefused",
                message=(
                    f"Orphan sweep: {unresolvable} scope record(s) could not be "
                    f"resolved, so {source_id} cannot be proven unreferenced"
                ),
                tags={"reason": "unresolvable_scope"},
            )
            return "undecided"
        return "orphan"

    @staticmethod
    def _may_reclaim(scopes_snapshot, dir_names) -> bool:
        """False when a store read that returned ZERO scopes must not be acted
        on.

        ``ScopeRepository.all()`` is a Redis SCAN loop: against an empty or
        wrong keyspace it returns no keys and no error, so "the store is
        empty" and "the store we are reading is not the store that owns
        these clones" are the same observation from in here — and only one
        of them makes deleting every clone dir correct. Refuse by default;
        ``SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE`` opts in where an
        empty store provably means no scopes exist.
        """
        if scopes_snapshot or not dir_names:
            return True
        if opal_server_config.SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE:
            logger.warning(
                "Orphan sweep: scope store returned NO scopes while {n} clone "
                "dirs exist — reclaiming them all "
                "(SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE is enabled)",
                n=len(dir_names),
            )
            return True
        logger.error(
            "Orphan sweep aborted: scope store returned NO scopes while {n} "
            "clone dirs exist — refusing to reclaim (that looks like a "
            "misconfigured or empty store, e.g. REDIS_URL on the wrong DB, a "
            "failover to an empty replica, or a stray FLUSHDB, not a wiped "
            "boot). Set SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE=true if an "
            "empty store really means no scopes exist here.",
            n=len(dir_names),
        )
        metrics.event(
            "ScopeOrphanSweepRefused",
            message=(
                f"Orphan sweep refused: store returned no scopes while "
                f"{len(dir_names)} clone dirs exist"
            ),
            tags={"reason": "empty_store"},
        )
        return False

    def _eligible_for_reclaim(self, candidates):
        """Narrow this pass's candidates to the ones it may actually delete.

        Two independent bounds, both about a store that answers *wrongly* rather
        than not at all — the case the empty-store guard cannot see:

        1. **Corroboration across passes.** A dir must look orphaned for
           ``_REQUIRED_ORPHAN_STREAK`` consecutive passes. A store that is
           briefly incomplete (a replica seconds behind a failover, an LRU
           eviction of ``permit.io/Scope:*`` keys — they are SET with no TTL, so
           they are evictable — a partial restore) answers correctly again by the
           next pass, its records reappear, and the streak resets before anything
           is deleted. A share-based check could never catch this: a store that is
           40% incomplete produces a 40% orphan set, comfortably inside any
           sane threshold, and the under-lock re-check reads the same degraded
           store so it confirms the wrong answer rather than catching it.
        2. **A per-pass count cap.** Bounds the blast radius of a store that is
           *persistently* wrong, and bounds the sweep's cost: only eligible dirs
           pay the per-candidate store read, so a pass is O(cap) reads rather
           than O(orphans x scopes).

        Nothing is leaked by either bound — a genuine backlog drains over
        consecutive passes instead of in one.
        """
        global _reclaim_cap_disabled_warned
        names = {name for name, _ in candidates}
        # Streak state is per-name and pruned to the current candidate set, so a
        # dir that stops looking orphaned (re-claimed, or reclaimed) starts over
        # and the dict cannot grow without bound.
        self._orphan_streak = {
            name: self._orphan_streak.get(name, 0) + 1 for name in names
        }
        corroborated = [
            (name, path)
            for name, path in candidates
            if self._orphan_streak[name] >= _REQUIRED_ORPHAN_STREAK
        ]
        waiting = len(candidates) - len(corroborated)
        if waiting:
            logger.info(
                "Orphan sweep: {n} candidate(s) awaiting corroboration (a dir must "
                "look orphaned for {k} consecutive passes before it is reclaimed)",
                n=waiting,
                k=_REQUIRED_ORPHAN_STREAK,
            )

        cap = opal_server_config.SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_PER_PASS
        if cap <= 0:
            # Disabling a destructive-path safety control deserves an audit line,
            # once. (The previous fraction-based knob had this backwards: typos
            # warned, while the values an operator would actually type to turn it
            # off were silent.)
            if not _reclaim_cap_disabled_warned:
                _reclaim_cap_disabled_warned = True
                logger.warning(
                    "SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_PER_PASS={cap} disables the "
                    "orphan sweep's per-pass reclaim cap; a store pointed at the "
                    "wrong keyspace can reclaim the whole clone tree in one pass.",
                    cap=cap,
                )
            return corroborated
        if len(corroborated) > cap:
            logger.warning(
                "Orphan sweep reclaiming {cap} of {n} corroborated orphan(s) this "
                "pass (SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_PER_PASS); the rest follow "
                "on later passes. A large backlog is expected after a deliberate "
                "SCOPES_REPO_CLONES_SHARDS reconfig — raise the cap to drain it "
                "faster. If no such change was made, check REDIS_URL: a store on "
                "the wrong keyspace makes every local clone look unreferenced.",
                cap=cap,
                n=len(corroborated),
            )
            metrics.event(
                "ScopeOrphanSweepCapped",
                message=(
                    f"Orphan sweep capped at {cap} reclaims this pass "
                    f"({len(corroborated)} corroborated)"
                ),
                tags={"reason": "reclaim_cap"},
            )
        return corroborated[:cap]

    async def sweep_orphans(self) -> None:
        """Reclaim clone dirs referencing no live scope. Leader-only.

        Covers crash-orphaned dirs, redis-wiped boots, and old-shard dirs
        after a SCOPES_REPO_CLONES_SHARDS reconfig. Runs after boot sync
        and after each periodic sync pass (settled state).

        Two-stage by design. One snapshot cheaply filters out clearly-live
        dirs — the common case, no per-dir I/O at all. Whatever still looks
        orphaned becomes a *candidate*, and every candidate is re-checked
        against its OWN fresh read taken under its own ``lock_source``
        before it can be deleted (``_classify_candidate``). The snapshot is
        only a pre-filter: a batched read reused across candidates goes
        stale as the loop deletes, and deleting a live tenant's clone on a
        stale read is not self-healing at the shipped defaults.

        Refusals and degradations, all conservative, all visible in the
        heartbeat and on a metric: a raising store read (next pass retries), a
        SUCCESSFUL zero-scope read while clone dirs exist (indistinguishable
        from a misdirected store — ``SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE``
        opts in), and candidates the store could not answer for (a timed-out
        read, or a record whose ``source_id`` will not derive) which are kept
        and reported as ``degraded`` rather than silently counted as "found
        nothing".

        What may actually be deleted is narrowed by ``_eligible_for_reclaim``:
        a dir must look orphaned across consecutive passes, and only a bounded
        number are reclaimed per pass. That is what covers a store answering
        *wrongly* — which no single read, however fresh, can detect.
        """
        sources_dir = GitPolicyFetcher.base_dir(self._base_dir)
        try:
            dir_names = await run_sync(_list_dir_names, str(sources_dir))
        except FileNotFoundError:
            # Nothing cloned yet. Still heartbeat: "the sweeper ran and there was
            # nothing to do" and "the sweeper died" must never look the same.
            dir_names, outcome, reclaimed = [], "skipped (no clone dir)", 0
        else:
            outcome, reclaimed = await self._sweep_pass(dir_names)

        # Heartbeat on EVERY exit path, with the outcome and whatever was
        # reclaimed before an abort: a healthy no-op sweep (reclaimed=0) is the
        # common case and must stay visible, and an aborted pass must not look
        # like one — nor silently discard the count of what it already deleted.
        logger.info(
            "Orphan sweep {outcome}: scanned {scanned} clone dirs, reclaimed "
            "{reclaimed}",
            outcome=outcome,
            scanned=len(dir_names),
            reclaimed=reclaimed,
        )

    async def _reclaim_and_confirm(self, name: str, safe_path: str) -> bool:
        """Remove one orphan clone dir and broadcast its confirmation.

        Runs as its own task so a cancelled sweep cannot delete the directory and
        skip the broadcast. Returns whether the dir is gone.

        The repo_locks pop stays BEFORE the publish, per the ordering documented
        in purge_source_if_unshared: publish() runs local subscribers inline and
        handle_purge_message re-enters lock_source, so popping first makes it mint
        a fresh lock instead of deadlocking on the held one.
        """
        GitPolicyFetcher.forget_repo(safe_path)
        GitPolicyFetcher.repos_last_fetched.pop(name, None)
        removed = False
        try:
            await run_sync(shutil.rmtree, safe_path)
            removed = True
        except FileNotFoundError:
            removed = True  # already gone — the intended end state
        except OSError as e:
            if os.path.islink(safe_path):
                # scandir's is_dir() follows symlinks, so a symlink named like a
                # source id is enumerated and then refused by rmtree. Containment
                # held (the target is untouched), but this dir can never be
                # reclaimed — an anomaly worth an error, not a recurring
                # "reclaim failed" warning.
                logger.error(
                    "Orphan sweep found a SYMLINK where a clone dir should be, "
                    "refusing to follow it: {path} ({err})",
                    path=safe_path,
                    err=repr(e),
                )
            else:
                logger.warning(f"Failed to reclaim orphan {safe_path}: {e!r}")
        finally:
            GitPolicyFetcher.repo_locks.pop(name, None)
        if removed and self._pubsub_endpoint is not None:
            await self._pubsub_endpoint.publish(
                [opal_server_config.SCOPES_PURGE_CHANNEL],
                ScopePurgeCommand(
                    source_id=name,
                    clone_path=safe_path,
                    scope_id="",
                    reason="orphan",
                    confirmed=True,
                ).dict(),
            )
        return removed

    async def _sweep_pass(self, dir_names) -> tuple:
        """One sweep pass.

        Returns ``(outcome, reclaimed)`` for the heartbeat.
        """
        try:
            snapshot = await self._scopes.all()  # one scan; filters the bulk
        except Exception as e:
            logger.warning(f"Orphan sweep aborted, scope scan failed: {e!r}")
            # The exception TYPE only: `repr(e)` here would be a pydantic
            # ValidationError over a tenant scope record, and metrics.event is a
            # separate egress from the logs — the global redact_url_in_text log
            # patcher does not cover it. The full repr stays in the log above.
            metrics.event(
                "ScopeOrphanSweepRefused",
                message=(
                    f"Orphan sweep aborted: scope store scan failed "
                    f"({len(dir_names)} dirs on disk)"
                ),
                tags={"reason": "scan_failed", "error": type(e).__name__},
            )
            return "aborted (scope scan failed)", 0

        # An operator who enabled the empty-store reclaim has already declared
        # intent for exactly this mass reclaim, so the plausibility ceiling below
        # must not then veto it (it would make the opt-in a no-op on any tree of
        # more than one dir).
        deliberate_mass_reclaim = not snapshot

        # Precompute the live source_ids ONCE (O(scopes)) so the per-dir filter
        # below is an O(1) set lookup, instead of re-walking the whole snapshot
        # and recomputing two sha256 per (dir, scope) pair — that made the filter
        # O(dirs x scopes) and, with no await in the hot path, blocked the
        # leader's event loop. A scope whose source_id() derivation raises is
        # skipped here (logged), so its dir becomes a candidate — and its
        # under-lock re-check hits the same raise and conservatively keeps it.
        live_source_ids = set()
        for s in snapshot:
            if not isinstance(s.policy, GitPolicyScopeSource):
                continue
            try:
                live_source_ids.add(GitPolicyFetcher.source_id(s.policy))
            except Exception as e:
                logger.warning(
                    "Orphan sweep: could not derive source_id for scope "
                    "{scope_id}; its clone falls to the under-lock re-check: {err}",
                    scope_id=s.scope_id,
                    err=repr(e),
                )

        # Validate dir names BEFORE anything counts them — the same SECURITY
        # invariant every other deletion path enforces via _confined_clone_path.
        # A name the clone path never created is left untouched, and it must not
        # appear in any guard's arithmetic either: a name that can never be a
        # candidate would otherwise pad the tree size and buy headroom for free.
        validated = []
        for name in dir_names:
            safe_path = _confined_clone_path(self._base_dir, name)
            if safe_path is None:
                logger.warning(
                    "Orphan sweep skipping unrecognized clone dir (name is not a "
                    "source id): {name}",
                    name=name,
                )
                continue
            validated.append((name, safe_path))
        clone_dirs = [name for name, _ in validated]

        # Judged against validated names only: one stray non-clone entry under
        # git_sources/ (an operator's backup dir, a lost+found on a PVC, a
        # symlink — scandir follows them) would otherwise make a legitimately
        # empty store report "N clone dirs exist" and refuse every pass forever,
        # with a count that was never clone dirs.
        if not self._may_reclaim(snapshot, clone_dirs):
            return "aborted (empty store)", 0

        # Cheap filter: clearly live -> keep (O(1) set lookup, no per-dir I/O).
        candidates = [
            (name, path) for name, path in validated if name not in live_source_ids
        ]

        eligible = (
            candidates
            if deliberate_mass_reclaim
            else self._eligible_for_reclaim(candidates)
        )

        reclaimed = 0
        undecided = 0
        for i, (name, safe_path) in enumerate(eligible):
            # Yield periodically so a very large clone tree cannot starve the loop
            # between awaits, and because an uncontended lock_source does not
            # yield on its own.
            if i and i % _YIELD_EVERY == 0:
                await asyncio.sleep(0)
            async with GitPolicyFetcher.lock_source(name):
                # EVERY exit from this block pops the repo_locks entry lock_source
                # minted via setdefault (see the `finally` below). A candidate is by
                # definition a source no live scope claims, so leaving that entry
                # behind is a stray lock (invariant I4) — and the keep/abort paths
                # need the pop as much as the deletion paths, since they are reached
                # precisely when the store could NOT confirm the source is live.
                try:
                    # Authoritative, under THIS source's lock (see
                    # _classify_candidate for why it cannot be hoisted out of the
                    # loop): the lock excludes a concurrent clone/fetch for the
                    # source, and the read inside it is what makes "no live scope
                    # claims this dir" true at the moment we delete.
                    verdict = await self._classify_candidate(name, clone_dirs)
                    if verdict == "abort":
                        return "aborted (empty store mid-pass)", reclaimed
                    if verdict == "claimed":
                        continue
                    if verdict == "undecided":
                        # The store could not answer for this candidate (timed-out
                        # read, or a record whose source_id will not derive). Kept,
                        # and counted so the heartbeat cannot call the pass complete.
                        undecided += 1
                        continue
                    if git_op_in_flight(name):
                        # A lingering (timed-out) git op still touches the repo on a
                        # pool thread, so defer the dir removal + handle free to a
                        # later sweep (freeing now risks a crash). But DRAIN the
                        # event-loop-side entries under the held lock — including the
                        # repo_locks entry lock_source just minted for this candidate
                        # (via setdefault) — or that lock leaks as a stray with no
                        # live scope (invariant I4). Mirrors purge_source_if_unshared's
                        # in-flight branch.
                        logger.info(f"Orphan sweep deferring {name}: git op in flight")
                        GitPolicyFetcher.repos_last_fetched.pop(name, None)
                        continue
                    logger.info("Reclaiming orphan clone dir: {path}", path=safe_path)
                    # Delete + confirm as ONE unit, owned by the set the watcher's
                    # bounded shutdown drain awaits. A SIGTERM lands as a cancellation
                    # at the rmtree await, but run_sync dispatches to the loop's
                    # default executor, so the thread finishes and the directory goes
                    # regardless — while everything after it (the repo_locks pop and
                    # the confirmation) would be skipped. That leaves every other
                    # worker holding a pygit2 handle and a repos_last_fetched entry
                    # for a directory that no longer exists: the exact leak this
                    # series closes. Shielded here so the sweep's cancellation cannot
                    # take the unit with it.
                    unit = asyncio.create_task(
                        self._reclaim_and_confirm(name, safe_path)
                    )
                    self._pending_purges.add(unit)
                    unit.add_done_callback(self._pending_purges.discard)
                    if await asyncio.shield(unit):
                        reclaimed += 1
                finally:
                    # Under the held lock: EVERY exit from this block pops the
                    # entry lock_source minted via setdefault. A candidate is by
                    # definition a source no live scope claims, so leaving it
                    # behind is a stray lock (invariant I4) — and the keep/abort
                    # paths need the pop as much as the deletion path, since they
                    # are reached precisely when the store could NOT confirm the
                    # source is live. (The deletion unit pops it too, before its
                    # publish; popping twice is a no-op.)
                    GitPolicyFetcher.repo_locks.pop(name, None)

        if undecided:
            # A pass that could not DECIDE is not a pass that found nothing. The
            # heartbeat is what a monitor watches, so it must not read "complete"
            # while the leak backstop is effectively off for those candidates.
            return f"degraded ({undecided} candidate(s) unresolvable)", reclaimed
        return "complete", reclaimed
