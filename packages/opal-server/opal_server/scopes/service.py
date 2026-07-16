import datetime
import shutil
from functools import partial
from pathlib import Path
from typing import List, Optional, Set, cast

import git
from ddtrace import tracer
from fastapi_websocket_pubsub import PubSubEndpoint
from opal_common.async_utils import run_sync
from opal_common.git_utils.commit_viewer import VersionedFile
from opal_common.http_utils import redact_url
from opal_common.logger import logger
from opal_common.schemas.policy import PolicyUpdateMessageNotification
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.topics.publisher import ScopedServerSideTopicPublisher
from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks
from opal_server.policy.watcher.callbacks import (
    create_policy_update,
    create_update_all_directories_in_repo,
)
from opal_server.scopes.scope_repository import (
    Scope,
    ScopeNotFoundError,
    ScopeRepository,
)


def is_rego_source_file(
    f: VersionedFile, extensions: Optional[List[str]] = None
) -> bool:
    """Filters only rego files or data.json files."""
    REGO = ".rego"
    JSON = ".json"
    OPA_JSON = "data.json"

    if extensions is None:
        extensions = [REGO, JSON]
    if JSON in extensions and f.path.suffix == JSON:
        return f.path.name == OPA_JSON
    return f.path.suffix in extensions


class NewCommitsCallbacks(PolicyFetcherCallbacks):
    def __init__(
        self,
        base_dir: Path,
        scope_id: str,
        source: GitPolicyScopeSource,
        pubsub_endpoint: PubSubEndpoint,
    ):
        self._scope_repo_dir = GitPolicyFetcher.repo_clone_path(base_dir, source)
        self._scope_id = scope_id
        self._source = source
        self._pubsub_endpoint = pubsub_endpoint

    async def on_update(self, previous_head: str, head: str):
        if previous_head == head:
            logger.debug(
                f"scope '{self._scope_id}': No new commits, HEAD is at '{head}'"
            )
            return

        logger.info(
            f"scope '{self._scope_id}': Found new commits: old HEAD was '{previous_head}', new HEAD is '{head}'"
        )
        if not self._scope_repo_dir.exists():
            logger.error(
                f"on_update({self._scope_id}) was triggered, but repo path is not found: {self._scope_repo_dir}"
            )
            return

        try:
            repo = git.Repo(self._scope_repo_dir)
        except git.GitError as exc:
            logger.error(
                f"Got exception for repo in path: {self._scope_repo_dir}, scope_id: {self._scope_id}, error: {exc}"
            )
            return

        notification: Optional[PolicyUpdateMessageNotification] = None
        predicate = partial(is_rego_source_file, extensions=self._source.extensions)
        if previous_head is None:
            notification = await create_update_all_directories_in_repo(
                repo.commit(head), repo.commit(head), predicate=predicate
            )
        else:
            notification = await create_policy_update(
                repo.commit(previous_head),
                repo.commit(head),
                self._source.extensions,
                predicate=predicate,
            )

        if notification is not None:
            await self.trigger_notification(notification)

    async def trigger_notification(self, notification: PolicyUpdateMessageNotification):
        logger.info(
            f"Triggering policy update for scope {self._scope_id}: {notification.dict()}"
        )
        async with ScopedServerSideTopicPublisher(
            self._pubsub_endpoint, self._scope_id
        ) as publisher:
            await publisher.publish(notification.topics, notification.update)


class ScopesService:
    def __init__(
        self,
        base_dir: Path,
        scopes: ScopeRepository,
        pubsub_endpoint: PubSubEndpoint,
    ):
        self._base_dir = base_dir
        self._scopes = scopes
        self._pubsub_endpoint = pubsub_endpoint

    async def sync_scope(
        self,
        scope_id: str = None,
        scope: Scope = None,
        hinted_hash: Optional[str] = None,
        force_fetch: bool = False,
        notify_on_changes: bool = True,
        req_time: datetime.datetime = None,
    ):
        if scope is None:
            assert scope_id, ValueError("scope_id not set for sync_scope")
            scope = await self._scopes.get(scope_id)

        with tracer.trace("scopes_service.sync_scope", resource=scope.scope_id):
            if not isinstance(scope.policy, GitPolicyScopeSource):
                logger.warning("Non-git scopes are currently not supported!")
                return
            source = cast(GitPolicyScopeSource, scope.policy)

            logger.debug(
                f"Sync scope: {scope.scope_id} (remote: {redact_url(source.url)}, branch: {source.branch}, req_time: {req_time})"
            )

            callbacks = PolicyFetcherCallbacks()
            if notify_on_changes:
                callbacks = NewCommitsCallbacks(
                    base_dir=self._base_dir,
                    scope_id=scope.scope_id,
                    source=source,
                    pubsub_endpoint=self._pubsub_endpoint,
                )

            fetcher = GitPolicyFetcher(
                self._base_dir,
                scope.scope_id,
                source,
                callbacks=callbacks,
            )

            try:
                await fetcher.fetch_and_notify_on_changes(
                    hinted_hash=hinted_hash, force_fetch=force_fetch, req_time=req_time
                )
            except Exception as e:
                logger.exception(
                    f"Could not fetch policy for scope {scope.scope_id}, got error: {e}"
                )

    async def delete_scope(self, scope_id: str):
        with tracer.trace("scopes_service.delete_scope", resource=scope_id):
            logger.info(f"Delete scope: {scope_id}")
            scope = await self._scopes.get(scope_id)

            if not isinstance(scope.policy, GitPolicyScopeSource):
                # Mirrors sync_scope: only git sources have a clone dir and
                # fetcher caches to clean up.
                logger.warning(
                    f"Scope {scope_id} has a non-git policy source, "
                    "deleting the scope record only"
                )
                await self._scopes.delete(scope_id)
                return

            deleted_source = scope.policy
            deleted_source_id = GitPolicyFetcher.source_id(deleted_source)
            scope_dir = GitPolicyFetcher.repo_clone_path(self._base_dir, deleted_source)

            # Clone dir, the `repos` handle cache, and `repos_last_fetched` are
            # all keyed by source_id (= the clone path). A sibling only shares
            # storage when it resolves to the same source_id; same url with a
            # different branch can shard to a different source_id (and a
            # different clone dir) when SCOPES_REPO_CLONES_SHARDS > 1, so gate on
            # source_id, not url — otherwise the deleted scope's clone + pygit2
            # handle leak.
            #
            # Serialize record-delete + sibling-check + purge on the source
            # lock: two concurrent sibling deletes could otherwise both read
            # the other as still-live (the check and the record delete span
            # separate store round-trips) and BOTH skip the purge, orphaning
            # the clone and cache entries permanently. Deleting our record
            # before re-checking makes the last deleter see no sharer.
            async with GitPolicyFetcher.lock_source(deleted_source_id):
                try:
                    await self._scopes.delete(scope_id)
                finally:
                    # The purge must stay reachable even when the record
                    # delete raises an ambiguous outcome (committed server-
                    # side, error surfaced to the client): the client retry
                    # then hits ScopeNotFoundError -> 204 no-op, and a purge
                    # gated on a clean delete would be permanently orphaned.
                    # If the delete genuinely failed the record survives,
                    # over-purging self-heals (the scope re-clones on its
                    # next sync), and the error still propagates as a 500.
                    await self._purge_source_cache_if_unshared(
                        deleted_source_id, scope_dir, scope_id
                    )

    async def _purge_source_cache_if_unshared(
        self, deleted_source_id: str, scope_dir: Path, scope_id: str
    ):
        """Remove the clone dir and the GitPolicyFetcher cache entries keyed by
        ``deleted_source_id``, unless a surviving scope still shares them.

        Must run under ``lock_source(deleted_source_id)``, after scope_id's
        record was deleted (so the last of two concurrent sibling deleters
        sees no sharer and purges).
        """
        sharing_scope_id = await self._find_scope_sharing_source(
            deleted_source_id, scope_id
        )
        if sharing_scope_id is not None:
            logger.info(
                f"Scope {sharing_scope_id} shares the same clone "
                "(source id), skipping clone deletion"
            )
            return
        # NOTE (PR3): delete must ultimately route through the leader
        # like put/refresh — only the leader should mutate the shared
        # clone tree. Today this purge is process-local best-effort
        # (the leader's caches leak until PR3's broadcast purge), and
        # a non-leader DELETE rmtree's the shared tree unserialized
        # against the leader's in-flight fetches (cross-process;
        # bounded and self-healing, but an invariant break).
        # The same class exists IN-process: a sync that loaded the
        # scope before this delete and acquires the fresh lock after
        # the purge re-clones and re-populates the caches for the dead
        # scope (found by the bed's randomized churn driver;
        # deterministic seed recorded there). PR3's purge routing must
        # include a scope-liveness check before clone.
        try:
            await run_sync(shutil.rmtree, str(scope_dir))
        except FileNotFoundError:
            pass  # never cloned (or already gone) — nothing to clean
        except OSError as e:
            logger.warning(
                f"Failed to remove clone dir {scope_dir} of deleted "
                f"scope {scope_id}: {e!r}"
            )
        GitPolicyFetcher.forget_repo(str(scope_dir))
        GitPolicyFetcher.repos_last_fetched.pop(deleted_source_id, None)
        # Popped while the lock is held: lock_source waiters re-check
        # the dict entry after acquiring and retry on the fresh lock.
        GitPolicyFetcher.repo_locks.pop(deleted_source_id, None)

    async def _find_scope_sharing_source(
        self, deleted_source_id: str, scope_id: str
    ) -> Optional[str]:
        """Return the id of a surviving scope that shares deleted_source_id, or
        None (= safe to purge).

        Must not be able to skip the purge by raising: scope_id's record
        is already deleted, so a client retry is a 204 no-op
        (ScopeNotFoundError) and the purge becomes permanently
        unreachable. all() does a full scan + Scope.parse_raw — a
        transient store error or one malformed record throws. Over-
        purging self-heals (a surviving sibling re-clones on its next
        sync); under-purging is a permanent leak.
        """
        try:
            return next(
                (
                    s.scope_id
                    for s in await self._scopes.all()
                    if s.scope_id != scope_id
                    and isinstance(s.policy, GitPolicyScopeSource)
                    and GitPolicyFetcher.source_id(s.policy) == deleted_source_id
                ),
                None,
            )
        except Exception as e:
            logger.warning(
                f"sibling check failed after deleting scope "
                f"{scope_id}; purging defensively: {e!r}"
            )
            return None

    async def sync_scopes(self, only_poll_updates=False, notify_on_changes=True):
        with tracer.trace("scopes_service.sync_scopes"):
            scopes = await self._scopes.all()
            if only_poll_updates:
                # Only sync scopes that have polling enabled (in a periodic check)
                scopes = [scope for scope in scopes if scope.policy.poll_updates]

            logger.info(
                f"OPAL Scopes: syncing {len(scopes)} scopes in the background (polling updates: {only_poll_updates})"
            )

            fetched_source_ids = set()
            skipped_scopes = []
            for scope in scopes:
                src_id = GitPolicyFetcher.source_id(scope.policy)

                # Give priority to scopes that have a unique url per shard (so we'll clone all repos asap)
                if src_id in fetched_source_ids:
                    skipped_scopes.append(scope)
                    continue

                await self._sync_snapshotted_scope(
                    scope, force_fetch=True, notify_on_changes=notify_on_changes
                )
                fetched_source_ids.add(src_id)

            for scope in skipped_scopes:
                # No need to refetch the same repo, just check for changes
                await self._sync_snapshotted_scope(
                    scope, force_fetch=False, notify_on_changes=notify_on_changes
                )

    async def _sync_snapshotted_scope(
        self, scope: Scope, force_fetch: bool, notify_on_changes: bool
    ):
        """Sync one scope taken from a (possibly stale) all() snapshot,
        swallowing per-scope errors so the sweep continues.

        Passes scope_id (not the snapshot object) so sync_scope re-gets
        fresh state right before use — a delete that landed after the
        snapshot surfaces as ScopeNotFoundError instead of re-cloning a
        dead scope's repo and re-populating the fetcher caches for it.
        """
        try:
            await self.sync_scope(
                scope_id=scope.scope_id,
                force_fetch=force_fetch,
                notify_on_changes=notify_on_changes,
            )
        except ScopeNotFoundError:
            logger.info(
                f"scope {scope.scope_id} was deleted while sync was queued, skipping"
            )
        except Exception:
            logger.exception(f"sync_scope failed for {scope.scope_id}")
