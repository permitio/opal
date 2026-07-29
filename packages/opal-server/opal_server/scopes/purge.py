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
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, git_op_in_flight
from pydantic import BaseModel, ValidationError

# \Z (not $) so a trailing newline can't sneak past validation: in Python `$`
# also matches just before a final "\n", so "<64hex>-0\n" would wrongly pass.
_SOURCE_ID_RE = re.compile(r"\A[0-9a-f]{64}-\d+\Z")

# How many orphan-sweep candidates share one fresh store read (see
# LeaderScopePurger._fresh_live_source_ids). Trades Redis round trips against how
# stale that read can be when a dir is deleted; also the loop's yield cadence.
_FRESH_READ_EVERY = 200


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
            # nothing waits on. The next leader's boot sweep reclaims it.
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
                sharer = await find_scope_sharing_source(self._scopes, cmd.source_id)
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

    async def _fresh_live_source_ids(self, dir_names) -> Optional[set]:
        """Live source ids from a FRESH store read, or None if this pass must
        abort.

        Taken once per ``_FRESH_READ_EVERY`` candidates rather than once per
        candidate: a per-candidate read is a full Redis SCAN plus a parse per
        record plus two sha256 per live scope, i.e. O(orphans x scopes)
        sequential round trips in exactly the passes where every dir is a
        candidate (a ``SCOPES_REPO_CLONES_SHARDS`` reconfig, an opted-in
        wiped-store boot). Re-reading on a cadence rather than once for the whole
        pass bounds how stale this set can be at the moment a dir is deleted, so
        a PUT that re-claims a source mid-pass is seen within one batch.
        """
        try:
            fresh = await self._scopes.all()
        except Exception as e:
            logger.warning(f"Orphan sweep aborted, fresh re-check scan failed: {e!r}")
            return None
        if not self._may_reclaim(fresh, dir_names):
            return None
        try:
            return {
                GitPolicyFetcher.source_id(s.policy)
                for s in fresh
                if isinstance(s.policy, GitPolicyScopeSource)
            }
        except Exception as e:
            # Same conservative bias the per-candidate re-check had: an
            # underivable scope means we cannot prove any candidate is
            # unreferenced, so KEEP everything and retry next pass. The snapshot
            # loop already logged which scope is broken.
            logger.warning(
                f"Orphan sweep aborted, could not derive the fresh live source "
                f"set (a scope's source_id raised): {e!r}"
            )
            return None

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
        return False

    async def sweep_orphans(self) -> None:
        """Reclaim clone dirs referencing no live scope. Leader-only.

        Covers crash-orphaned dirs, redis-wiped boots, and old-shard dirs
        after a SCOPES_REPO_CLONES_SHARDS reconfig. Runs after boot sync
        and after each periodic sync pass (settled state).

        Hybrid: one snapshot cheaply filters out clearly-live dirs (the
        common case — no per-dir scan at all). Only dirs that look
        orphaned in that snapshot are re-checked against ONE fresh
        ``scopes.all()`` read, taken for the whole candidate batch, before
        each deletion under ``lock_source``.

        A store error must never read as "no scopes exist" (would rmtree
        every live clone) — abort; next pass retries. Neither must a
        SUCCESSFUL empty result: ``ScopeRepository.all()`` is a Redis SCAN
        loop that returns zero keys, no error, against a wrong/empty
        keyspace, so an empty store with clone dirs present is treated as a
        misconfiguration and aborted unless
        ``SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE`` says otherwise.

        Freshness is per BATCH of ``_FRESH_READ_EVERY`` candidates, not per
        candidate: a per-candidate scan was O(orphans x scopes) Redis round
        trips in exactly the passes that make every dir a candidate — a
        shard reconfig or an opted-in wiped store. The residual window is
        a re-claim landing between a batch's read and this pass reaching
        that dir; the cost there is a spurious reclaim plus a re-clone on
        the scope's next sync, not lost policy.
        """
        sources_dir = GitPolicyFetcher.base_dir(self._base_dir)
        try:
            dir_names = await run_sync(_list_dir_names, str(sources_dir))
        except FileNotFoundError:
            return  # nothing cloned yet

        try:
            snapshot = await self._scopes.all()  # one scan; filters the bulk
        except Exception as e:
            logger.warning(f"Orphan sweep aborted, scope scan failed: {e!r}")
            return

        if not self._may_reclaim(snapshot, dir_names):
            return

        # Precompute the live source_ids ONCE (O(scopes)) so the per-dir filter
        # below is an O(1) set lookup, instead of re-walking the whole snapshot
        # and recomputing two sha256 per (dir, scope) pair — that made the filter
        # O(dirs x scopes) and, with no await in the hot path, blocked the
        # leader's event loop. A scope whose source_id() derivation raises is
        # skipped here (logged), so its dir becomes a candidate — and the fresh
        # batch derivation below hits the same raise and aborts the pass, which
        # is the conservative bias: never delete a dir we cannot prove orphaned.
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

        candidates = []
        for name in dir_names:
            # Validate the dir name is a real source id BEFORE it can reach
            # rmtree — the same SECURITY invariant every other deletion path
            # enforces via _confined_clone_path. A name the clone path never
            # created (not a source id) is left untouched, never swept.
            safe_path = _confined_clone_path(self._base_dir, name)
            if safe_path is None:
                logger.warning(
                    "Orphan sweep skipping unrecognized clone dir (name is not a "
                    "source id): {name}",
                    name=name,
                )
                continue
            # Cheap filter: clearly live -> keep (O(1) set lookup, no per-dir I/O).
            if name in live_source_ids:
                continue
            candidates.append((name, safe_path))

        reclaimed = 0
        fresh_live = None
        for i, (name, safe_path) in enumerate(candidates):
            if i % _FRESH_READ_EVERY == 0:
                # One fresh read per batch of candidates (not per candidate),
                # which also yields, so a very large clone tree can't starve the
                # event loop: every other check in this loop is O(1) and an
                # uncontended lock_source does not yield on its own.
                fresh_live = await self._fresh_live_source_ids(dir_names)
                if fresh_live is None:
                    return
            async with GitPolicyFetcher.lock_source(name):
                # Taken under the lock so a PUT that re-claimed this source
                # mid-sweep (its sync takes the same lock, cloning being
                # leader-local) cannot be half-observed: either its record is in
                # fresh_live, or its clone finished after this check and the
                # dir we remove is rebuilt by the next sync.
                if name in fresh_live:
                    continue  # re-claimed since the snapshot
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
                    GitPolicyFetcher.repo_locks.pop(name, None)
                    continue
                logger.info("Reclaiming orphan clone dir: {path}", path=safe_path)
                GitPolicyFetcher.forget_repo(safe_path)
                GitPolicyFetcher.repos_last_fetched.pop(name, None)
                try:
                    await run_sync(shutil.rmtree, safe_path)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.warning(f"Failed to reclaim orphan {safe_path}: {e!r}")
                    continue
                # Popped under the held lock AND deliberately BEFORE the
                # confirmation publish below — see purge_source_if_unshared for
                # why moving it after the publish deadlocks.
                GitPolicyFetcher.repo_locks.pop(name, None)
                reclaimed += 1
                if self._pubsub_endpoint is not None:
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

        # Heartbeat: a healthy no-op sweep (reclaimed=0) is the common case and
        # must still be visible in Datadog, so on-call can confirm the leak
        # backstop actually ran rather than silently died.
        logger.info(
            "Orphan sweep complete: scanned {scanned} clone dirs, reclaimed {reclaimed}",
            scanned=len(dir_names),
            reclaimed=reclaimed,
        )
