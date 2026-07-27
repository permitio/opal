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

_SOURCE_ID_RE = re.compile(r"^[0-9a-f]{64}-\d+$")


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
    clone_path: str  # carried explicitly: the scope record is already gone
    scope_id: str  # logging / tracing only
    reason: str  # "delete" | "repoint" | "orphan" — logging only
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
    purge_local_memory(cmd.source_id, safe_path)


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
        # publish() awaits subscriber callbacks inline — never do lock-waiting
        # disk work on the publisher's request path (DELETE/PUT latency is
        # bounded by contract). The purge proceeds in the background.
        task = asyncio.create_task(self._purge_and_log(cmd))
        self._pending_purges.add(task)
        task.add_done_callback(self._pending_purges.discard)
        return task

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

    async def sweep_orphans(self) -> None:
        """Reclaim clone dirs referencing no live scope.

        Covers crash-orphaned dirs, redis-wiped boots, and old-shard
        dirs after a SCOPES_REPO_CLONES_SHARDS reconfig. Leader-only;
        runs after boot sync and after each periodic sync pass (settled
        state).
        """
        sources_dir = GitPolicyFetcher.base_dir(self._base_dir)
        try:
            entries = await run_sync(os.listdir, str(sources_dir))
        except FileNotFoundError:
            return  # nothing cloned yet

        try:
            live = {
                GitPolicyFetcher.source_id(s.policy)
                for s in await self._scopes.all()
                if isinstance(s.policy, GitPolicyScopeSource)
            }
        except Exception as e:
            # A transient store error must NOT read as "no scopes exist" —
            # that would rmtree every live clone. Abort; next pass retries.
            logger.warning(f"Orphan sweep aborted, scope scan failed: {e!r}")
            return

        for name in entries:
            path = sources_dir / name
            if name in live or not path.is_dir():
                continue
            async with GitPolicyFetcher.lock_source(name):
                # Re-check under the lock: a PUT may have claimed this
                # source while we swept (cloning is also leader-local under
                # this same lock, so the serialization is sound). A raising
                # re-check keeps the dir (conservative — opposite bias to
                # the delete path, where the record is known-gone).
                try:
                    still_orphan = name not in {
                        GitPolicyFetcher.source_id(s.policy)
                        for s in await self._scopes.all()
                        if isinstance(s.policy, GitPolicyScopeSource)
                    }
                except Exception:
                    continue
                if not still_orphan:
                    continue
                if git_op_in_flight(name):
                    # Unlike purge_source_if_unshared's in-flight branch, there's
                    # no immediate lock/timestamp drain here: an orphan has no
                    # live scope and no waiter blocked on this lock to free, so
                    # deferring the whole entry to the next sweep pass is
                    # sufficient (the entry may not even be in the caches).
                    logger.info(f"Orphan sweep skipping {name}: git op in flight")
                    continue
                logger.info(f"Reclaiming orphan clone dir: {path}")
                GitPolicyFetcher.forget_repo(str(path))
                GitPolicyFetcher.repos_last_fetched.pop(name, None)
                try:
                    await run_sync(shutil.rmtree, str(path))
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.warning(f"Failed to reclaim orphan {path}: {e!r}")
                    continue
                GitPolicyFetcher.repo_locks.pop(name, None)  # under the lock
                if self._pubsub_endpoint is not None:
                    await self._pubsub_endpoint.publish(
                        [opal_server_config.SCOPES_PURGE_CHANNEL],
                        ScopePurgeCommand(
                            source_id=name,
                            clone_path=str(path),
                            scope_id="",
                            reason="orphan",
                            confirmed=True,
                        ).dict(),
                    )
