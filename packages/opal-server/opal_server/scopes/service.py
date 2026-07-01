import asyncio
import datetime
import shutil
from functools import partial
from pathlib import Path
from typing import List, Optional, Set, cast

import git
from ddtrace import tracer
from fastapi_websocket_pubsub import PubSubEndpoint
from opal_common.git_utils.commit_viewer import VersionedFile
from opal_common.logger import logger
from opal_common.schemas.policy import PolicyUpdateMessageNotification
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.topics.publisher import ScopedServerSideTopicPublisher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks
from opal_server.policy.watcher.callbacks import (
    create_policy_update,
    create_update_all_directories_in_repo,
)
from opal_server.scopes.scope_repository import Scope, ScopeRepository


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
                f"Sync scope: {scope.scope_id} (remote: {source.url}, branch: {source.branch}, req_time: {req_time})"
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
            deleted_source = cast(GitPolicyScopeSource, scope.policy)
            deleted_source_id = GitPolicyFetcher.source_id(deleted_source)
            scope_dir = GitPolicyFetcher.repo_clone_path(self._base_dir, deleted_source)

            # Clone dir, the `repos` handle cache, and `repos_last_fetched` are
            # all keyed by source_id (= the clone path). A sibling only shares
            # storage when it resolves to the same source_id; same url with a
            # different branch can shard to a different source_id (and a
            # different clone dir) when SCOPES_REPO_CLONES_SHARDS > 1, so gate on
            # source_id, not url — otherwise the deleted scope's clone + pygit2
            # handle leak.
            other_scopes = [
                s for s in await self._scopes.all() if s.scope_id != scope_id
            ]
            source_id_shared = any(
                isinstance(s.policy, GitPolicyScopeSource)
                and GitPolicyFetcher.source_id(s.policy) == deleted_source_id
                for s in other_scopes
            )

            # Serialize the filesystem + cache mutation against an in-flight
            # fetch of the same source so a delete cannot race a concurrent
            # sync_scope (see PR4 bounded-concurrency loading).
            async with GitPolicyFetcher.source_lock(deleted_source_id):
                if source_id_shared:
                    logger.info(
                        "Another scope shares the same clone (source id), skipping clone deletion"
                    )
                else:
                    shutil.rmtree(scope_dir, ignore_errors=True)
                    GitPolicyFetcher.forget_repo(str(scope_dir))
                    GitPolicyFetcher.repos_last_fetched.pop(deleted_source_id, None)

            await self._scopes.delete(scope_id)

    async def sync_scopes(self, only_poll_updates=False, notify_on_changes=True):
        with tracer.trace("scopes_service.sync_scopes"):
            scopes = await self._scopes.all()
            if only_poll_updates:
                # Only sync scopes that have polling enabled (in a periodic check)
                scopes = [scope for scope in scopes if scope.policy.poll_updates]

            concurrency = max(1, opal_server_config.SCOPES_SYNC_CONCURRENCY)
            logger.info(
                f"OPAL Scopes: syncing {len(scopes)} scopes "
                f"(concurrency={concurrency}, polling updates: {only_poll_updates})"
            )

            # Pass 1: fetch each distinct source once (force_fetch). Pass 2: scopes that
            # share an already-fetched source only re-check locally (no network).
            fetched_source_ids = set()
            first_pass = []
            second_pass = []
            for scope in scopes:
                src_id = GitPolicyFetcher.source_id(scope.policy)

                # Give priority to scopes that have a unique url per shard (so we'll clone all repos asap)
                if src_id in fetched_source_ids:
                    second_pass.append(scope)
                else:
                    fetched_source_ids.add(src_id)
                    first_pass.append(scope)

            await self._sync_scope_batch(
                first_pass,
                force_fetch=True,
                notify_on_changes=notify_on_changes,
                concurrency=concurrency,
            )
            await self._sync_scope_batch(
                second_pass,
                force_fetch=False,
                notify_on_changes=notify_on_changes,
                concurrency=concurrency,
            )

    async def _sync_scope_batch(
        self, scopes, *, force_fetch, notify_on_changes, concurrency
    ):
        if not scopes:
            return
        semaphore = asyncio.Semaphore(concurrency)

        async def _one(scope):
            async with semaphore:
                try:
                    await self.sync_scope(
                        scope=scope,
                        force_fetch=force_fetch,
                        notify_on_changes=notify_on_changes,
                    )
                except Exception:
                    logger.exception(f"sync_scope failed for {scope.scope_id}")

        await asyncio.gather(*(_one(scope) for scope in scopes))
