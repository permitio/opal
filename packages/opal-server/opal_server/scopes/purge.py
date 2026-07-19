"""Fleet-wide purge of GitPolicyFetcher caches (PR3 of the leak series).

Every worker subscribes ``handle_purge_message`` to SCOPES_PURGE_CHANNEL at
startup (see ``server.py``) and drops its in-memory cache entries for the
purged source. The leader additionally registers ``LeaderScopePurger.handle``
(at watcher start) which removes the clone dir — only the leader mutates the
clone tree.
"""
from typing import Any, Optional

from opal_common.logger import logger
from pydantic import BaseModel, ValidationError

from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, git_op_in_flight


class ScopePurgeCommand(BaseModel):
    source_id: str  # cache key for repos_last_fetched / repo_locks
    clone_path: str  # carried explicitly: the scope record is already gone
    scope_id: str  # logging / tracing only
    reason: str  # "delete" | "repoint" | "orphan" — logging only


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
    logger.info(
        "Purging local caches for source {source_id} (scope {scope_id}, {reason})",
        source_id=cmd.source_id,
        scope_id=cmd.scope_id,
        reason=cmd.reason,
    )
    purge_local_memory(cmd.source_id, cmd.clone_path)


async def subscribe_worker_purge_handler(endpoint) -> None:
    await endpoint.subscribe(
        [opal_server_config.SCOPES_PURGE_CHANNEL], handle_purge_message
    )
