"""Fleet-wide purge of GitPolicyFetcher caches (PR3 of the leak series).

Every worker subscribes ``handle_purge_message`` to SCOPES_PURGE_CHANNEL at
startup (see ``server.py``) and drops its in-memory cache entries for the
purged source. The leader additionally registers ``LeaderScopePurger.handle``
(at watcher start), which sibling-checks and then authorizes that drop by
broadcasting the confirmation.

WHO MUTATES THE CLONE TREE. Not "only the leader" — that claim was in this
docstring and was never true. The leader is the only mutator on SYNC paths
(clone/fetch are leader-only). A delete additionally removes the dir on the
worker that SERVED the DELETE, best-effort, exactly as master did
(``ScopesService._purge_local_clone_best_effort``). Its guards — ``lock_source``
(an asyncio.Lock) and ``git_op_in_flight`` (a module-global set) — are
PROCESS-LOCAL, so they do not serialize that worker against the leader cloning
the same source in a sibling process on the same pod. Master had the identical
exposure with no in-flight guard at all, so this is not a regression — but note
the branch does not reclaim that orphan either: delivering the purge broadcast
drains MEMORY on every worker and touches no disk. It is also not an invariant.
Closing it cross-process is PER-15612.

NOTE: the reconciliation sweep that reclaimed clone dirs referencing no live
scope was split out of this PR and is tracked as PER-15612. What remains here is
the purge driven by an actual scope delete/repoint.

There is therefore NO reconciliation of any kind in this PR, and exactly ONE
path RECLAIMS a clone dir — removes it and leaves it removed: the best-effort
local floor ``ScopesService.delete_scope`` spawns on the worker serving the
DELETE.

Two other ``rmtree`` sites exist and are not reclamation: ``git_fetcher``'s
invalid-repo recovery and ``_clone``'s partial-dir wipe both delete-and-replace
a dir they are about to re-create. Both run under ``lock_source`` and target
``self._repo_path``, derived from ``GitPolicyFetcher.source_id(source)`` — a
sha256 digest of the URL, never wire input. An audit of "can caller-controlled
input reach an rmtree?" has to account for all three. That is
master's behaviour (master removed it inline there, with no broadcast involved),
kept so a dropped broadcast does not regress against the merge base.

What that leaves on disk, stated plainly because nothing else will reclaim it:

- a DELETE's dir on every pod EXCEPT the serving one, when the broadcast is
  lost — and the broadcast is droppable at shipped defaults, since a DELETE
  usually lands on a non-leader worker (SERVER_WORKER_COUNT defaults to the
  core count) and must traverse the broadcaster, while a leader keeps a reader
  alive only if it has a connected client or STATISTICS_ENABLED (default False).
  The LEADER always has a reader — its watcher enters a listening context
  unconditionally (policy/watcher/task.py) — so it is non-leader workers that
  can be deaf, not the leader; a backbone outage still loses it for everyone;
- a REPOINT's old dir on EVERY pod, always — there is no floor on that path;
- a dir whose source_id is unknowable because the prior record would not parse
  (see ``scopes/api.py``).

All three are PER-15612. The memory purge is unaffected by them: it is
authorized by the leader's confirmation and is self-healing in both directions.
"""
import asyncio
import re
from pathlib import Path
from typing import Any, Optional

from opal_common.logger import logger
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, git_op_in_flight
from pydantic import BaseModel, ValidationError

# \Z (not $) so a trailing newline can't sneak past validation: in Python `$`
# also matches just before a final "\n", so "<64hex>-0\n" would wrongly pass.
# [0-9], not \d: for a `str` pattern \d is Unicode and also matches e.g. Arabic-
# Indic digits. Containment is unaffected either way (the derived path stays
# under base_dir and could not exist), but the id this validates is a sha256
# hex digest + an ASCII shard index, so say that.
_SOURCE_ID_RE = re.compile(r"\A[0-9a-f]{64}-[0-9]+\Z")


def confined_clone_path(base_dir, source_id: str):
    """Derive the on-disk clone dir for ``source_id``, or ``None`` if the id is
    malformed.

    SECURITY: a purge command's ``clone_path`` field arrives over pub/sub and
    must NEVER reach the filesystem. ``source_id`` is a sha256 hex digest +
    shard index (no separators, no traversal), so the derived path is always
    confined to ``base_dir/git_sources``. The result is also the exact key used
    in ``GitPolicyFetcher.repos``.

    What a forged message can still reach, now that the disk reclaim is cut: a
    ``free()`` of a cached pygit2 handle under an attacker-chosen key (via
    ``purge_local_memory`` -> ``forget_repo``). It can no longer reach an
    ``rmtree`` — no wire-driven path in this module removes a directory, and the
    one remaining removal (``ScopesService``'s delete floor) derives its target
    from the stored scope record, not from a message. Keeping the validation is
    still right: it is the only thing standing between a forged ``source_id``
    and an arbitrary ``repos`` key, and it is what makes the confinement
    property survive PER-15612 putting an rmtree back on this path.
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
    # branches on reason. A repoint's old source still has a LIVE record (it
    # just moved), so an unreadable or unanswered scan can't be told apart from
    # "still shared" and the clone is kept; a delete's record is already gone,
    # so the same scan failure purges defensively — under-purging there is a
    # permanent leak. See LeaderScopePurger.purge_source_if_unshared.
    reason: str  # "delete" | "repoint"
    confirmed: bool = False  # set by the leader after the sibling-check;
    # memory handlers act only on confirmed commands


def purge_local_memory(source_id: str, clone_path: str) -> None:
    """Drop this process's in-memory cache entries for a source.

    Never pops ``repo_locks``: lock_source's recheck loop protects waiters,
    not a current holder — popping is only safe while holding the lock, which
    this function does not (its callers that DO hold it pop there). ``forget_repo`` is skipped while a
    git op is in flight: freeing a pygit2 handle a pool thread still uses
    (e.g. a lingering timed-out fetch) is a crash risk.

    A skipped free is NOT self-healing on this worker: ``forget_repo`` is
    otherwise only reached from the invalid-repo branch of a SYNC, and a purged
    source by construction has no live scope to sync. So a handle pinned by a
    lingering timed-out op stays cached for the life of the process. Nothing in
    this PR revisits it — that is PER-15612's job, along with the clone dir.
    """
    if not git_op_in_flight(source_id):
        GitPolicyFetcher.forget_repo(clone_path)
    GitPolicyFetcher.repos_last_fetched.pop(source_id, None)
    # Unconditionally, unlike forget_repo: this holds no handle a lingering
    # pool thread could still be reading, so the in-flight guard does not apply.
    # Dropped for the same reason as repos_last_fetched — the source has no live
    # scope on this worker any more, so a kept entry is counted in the
    # sources_in_backoff gauge for the life of the process, and would suppress
    # the first sync of a scope later re-created against the same URL.
    GitPolicyFetcher.forget_source_backoff(source_id)


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
    safe_path = confined_clone_path(opal_server_config.BASE_DIR, cmd.source_id)
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
    the caller owns the fail-open/fail-closed policy for that.
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


class LeaderScopePurger:
    """Leader-only: removes clone dirs for purged sources.

    Registered on SCOPES_PURGE_CHANNEL when leadership is acquired (the
    watcher task's start). It performs the sibling check no other worker can
    do, and authorizes the fleet's memory purge; it does not touch the clone
    tree (see the module docstring on who does).
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
            # either be abandoned by that bounded drain or publish a
            # confirmation nothing waits on. NOTHING recovers this: no periodic
            # reconciliation exists in this PR, and no later purge will name the
            # source (the record is already gone), so the fleet keeps its cache
            # entries for it until PER-15612 lands. The serving worker's local
            # floor has still reclaimed its own pod's clone dir.
            logger.info(
                f"Ignoring purge request for {cmd.source_id} ({cmd.reason}): "
                "purger is stopping"
            )
            return None
        # publish() awaits subscriber callbacks inline — never do lock-waiting
        # disk work on the publisher's request path (DELETE/PUT latency is
        # bounded by contract). The purge proceeds in the background.
        return self._schedule(self._purge_and_log(cmd))

    def signal_stop(self) -> None:
        """Refuse new purge requests from ``handle`` (idempotent)."""
        self._stopping = True

    async def stop(self) -> None:
        """Await in-flight background purges so a shutdown can't abandon a
        sibling check mid-flight (or start a fresh one after the watcher
        stopped).

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

    def _schedule(self, coro) -> asyncio.Task:
        """Run ``coro`` detached, holding a strong ref so it can't be GC'd, and
        make ``stop()``'s drain wait for it."""
        task = asyncio.create_task(coro)
        self._pending_purges.add(task)
        task.add_done_callback(self._pending_purges.discard)
        return task

    async def purge_source_if_unshared(self, cmd: ScopePurgeCommand) -> None:
        """Leader-only: authorize the fleet-wide MEMORY purge for a source.

        Only the leader can sibling-check (it reads the scope store), so only
        the leader may authorize a memory purge: acting on the raw request
        would drop cache entries a surviving sibling scope still uses. It
        publishes the confirmation, and every worker's ``handle_purge_message``
        acts on that.

        This deliberately does NOT touch the clone tree. Disk reclaim on delete
        happens on the DELETE-serving worker at master's semantics
        (``ScopesService._purge_local_clone_best_effort``); distributed disk
        reclaim — a leader-side rmtree, a retry for a dir a lingering git op
        pins, and the reconciliation sweep — is PER-15612, where the reclaim
        policy is agreed before implementation. Under-purging disk leaks
        forever and over-purging forces a re-clone, so it has no self-healing
        direction; a memory purge self-heals both ways (a wrongly-dropped
        handle just re-opens on next use), which is why the two split here.
        """
        if confined_clone_path(self._base_dir, cmd.source_id) is None:
            logger.warning(
                f"Ignoring leader purge with malformed source_id: {cmd.source_id}"
            )
            return
        confirm = False
        async with GitPolicyFetcher.lock_source(cmd.source_id):
            # I4 is "no stray repo_locks key for a source NOBODY holds", so the
            # drain below covers the exits where we abandon the source — the two
            # fail-open returns, and the confirmed purge — but NOT the path where
            # a live sibling still shares it. Popping there is safe (lock_source
            # re-mints) but wrong: it churns a lock the sibling is using, and the
            # bed asserts the entry survives a sibling delete
            # (test_shared_repo_survives_sibling_scope_delete).
            minted = GitPolicyFetcher.repo_locks.get(cmd.source_id)
            try:
                try:
                    timeout = opal_server_config.SCOPES_STORE_READ_TIMEOUT
                    check = find_scope_sharing_source(self._scopes, cmd.source_id)
                    sharer = await (
                        asyncio.wait_for(check, timeout=timeout)
                        if timeout > 0
                        else check
                    )
                except asyncio.TimeoutError:
                    # Bounded because this read is held under lock_source and the
                    # Redis client has no socket timeout — an unreachable store
                    # would otherwise wedge this source's lock for the life of
                    # the process.
                    #
                    # Direction follows master's rule: over-purging self-heals,
                    # under-purging is a permanent leak. A repoint's old source
                    # may still be referenced, so an unanswered read must not be
                    # read as "unshared"; a delete's record is already gone.
                    if cmd.reason == "repoint":
                        logger.warning(
                            "Sibling check for {sid} timed out after {t}s on a "
                            "repoint; not confirming — the fleet keeps its cache "
                            "entries for this source until something names it "
                            "again",
                            sid=cmd.source_id,
                            t=timeout,
                        )
                        return
                    logger.warning(
                        "Sibling check for {sid} timed out after {t}s on {reason}; "
                        "confirming defensively — its record is already gone, so "
                        "withholding the purge would leak the fleet's cache "
                        "entries permanently (a surviving sibling re-opens its "
                        "handle on the next sync)",
                        sid=cmd.source_id,
                        t=timeout,
                        reason=cmd.reason,
                    )
                    sharer = None
                except Exception as e:
                    if cmd.reason == "repoint":
                        logger.warning(
                            f"Sibling check for {cmd.source_id} failed on repoint; "
                            f"not confirming: {e!r}"
                        )
                        return
                    logger.warning(
                        f"Sibling check for {cmd.source_id} failed on {cmd.reason}; "
                        f"confirming defensively: {e!r}"
                    )
                    sharer = None
                if sharer is not None:
                    logger.info(
                        f"Scope {sharer} still shares source {cmd.source_id}, "
                        "keeping the fleet's cache entries"
                    )
                    minted = None  # live source — leave its lock alone
                else:
                    confirm = True
                # Published under the lock: publish() runs local subscribers
                # inline, so the confirmation frees this process's cached pygit2
                # handle. Releasing the lock first would let a re-created scope's
                # sync acquire it, cache a fresh handle, and enter
                # _notify_on_changes — which holds the handle across an await and
                # then calls set_target() on it — while this stale confirmation
                # frees it underneath (use-after-free).
                if confirm and self._pubsub_endpoint is not None:
                    # LOAD-BEARING ORDER: pop BEFORE the publish. publish() runs
                    # local subscribers inline on this task, and
                    # handle_purge_message re-enters lock_source(source_id) — the
                    # same non-reentrant Lock still held here. Popping first makes
                    # its setdefault mint a FRESH lock instead of waiting on ours;
                    # popping after would wedge this source's lock permanently.
                    GitPolicyFetcher.repo_locks.pop(cmd.source_id, None)
                    await self._pubsub_endpoint.publish(
                        [opal_server_config.SCOPES_PURGE_CHANNEL],
                        cmd.copy(update={"confirmed": True}).dict(),
                    )
            finally:
                # Lock-identity guarded: the pop-before-publish above hands the
                # dict entry off, and the awaited publish lets another coroutine
                # mint a SUCCESSOR lock. Popping unconditionally here would
                # discard that successor while its holder still runs, putting two
                # coroutines inside lock_source for the same source at once.
                #
                # The identity check is what prevents that, on its own: after the
                # hand-off `minted` is no longer the mapped lock, so `is minted`
                # is False whether a successor appeared or the key is simply
                # absent. An explicit `minted = None` used to sit on that path as
                # well; it was removed because it is unreachable-as-true and so
                # could not be tested — mutating it changed nothing, while
                # mutating this check fails three tests.
                if (
                    minted is not None
                    and GitPolicyFetcher.repo_locks.get(cmd.source_id) is minted
                ):
                    GitPolicyFetcher.repo_locks.pop(cmd.source_id, None)
