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
            url = scope.policy.url

            scopes = await self._scopes.all()
            remove_repo_clone = True

            for scope in scopes:
                if scope.scope_id != scope_id and scope.policy.url == url:
                    logger.info(
                        f"found another scope with same remote url ({scope.scope_id}), skipping clone deletion"
                    )
                    remove_repo_clone = False
                    break

            if remove_repo_clone:
                scope_dir = GitPolicyFetcher.repo_clone_path(
                    self._base_dir, cast(GitPolicyScopeSource, scope.policy)
                )
                shutil.rmtree(scope_dir, ignore_errors=True)

            await self._scopes.delete(scope_id)

    async def sync_scopes(self, only_poll_updates=False, notify_on_changes=True):
        with tracer.trace("scopes_service.sync_scopes"):
            scopes = await self._scopes.all()
            if only_poll_updates:
                # Only sync scopes that have polling enabled (in a periodic check)
                scopes = [scope for scope in scopes if scope.policy.poll_updates]

            logger.info(
                f"OPAL Scopes: syncing {len(scopes)} scopes in the background (polling updates: {only_poll_updates})"
            )

            # Partition into distinct repos (cloned/fetched once, with priority
            # so every repo is pulled asap) and the scopes that merely reuse an
            # already-handled repo (checked for changes only).
            unique_scopes = []
            duplicate_scopes = []
            seen_source_ids = set()
            for scope in scopes:
                src_id = GitPolicyFetcher.source_id(scope.policy)
                if src_id in seen_source_ids:
                    duplicate_scopes.append(scope)
                else:
                    seen_source_ids.add(src_id)
                    unique_scopes.append(scope)

            # Bound concurrency to the dedicated git pool so one unreachable repo
            # only stalls its own slot (for the fetch timeout), not the whole
            # boot/poll pass. Phase 1 clones/fetches every distinct repo; phase 2
            # then checks the duplicates against those now-present repos.
            semaphore = asyncio.Semaphore(
                max(1, opal_server_config.SCOPES_GIT_MAX_WORKERS)
            )
            await self._sync_scopes_concurrently(
                unique_scopes,
                semaphore,
                force_fetch=True,
                notify_on_changes=notify_on_changes,
            )
            await self._sync_scopes_concurrently(
                duplicate_scopes,
                semaphore,
                force_fetch=False,
                notify_on_changes=notify_on_changes,
            )

    async def _sync_scopes_concurrently(
        self, scopes, semaphore, *, force_fetch, notify_on_changes
    ):
        """Sync ``scopes`` concurrently, bounded by ``semaphore``.

        Each scope's failure is logged and isolated so one bad repo
        never fails the whole pass.
        """

        async def _sync_one(scope):
            async with semaphore:
                try:
                    await self.sync_scope(
                        scope=scope,
                        force_fetch=force_fetch,
                        notify_on_changes=notify_on_changes,
                    )
                except Exception:
                    logger.exception(f"sync_scope failed for {scope.scope_id}")

        await asyncio.gather(*(_sync_one(scope) for scope in scopes))
