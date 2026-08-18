import asyncio
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
from opal_common.monitoring import metrics
from opal_common.schemas.policy import PolicyUpdateMessageNotification
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.topics.publisher import ScopedServerSideTopicPublisher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitConcurrencyLimitExceeded,
    GitPolicyFetcher,
    PolicyFetcherCallbacks,
    emit_sources_in_backoff,
    git_op_in_flight,
)
from opal_server.policy.watcher.callbacks import (
    create_policy_update,
    create_update_all_directories_in_repo,
)
from opal_server.scopes.purge import (
    ScopePurgeCommand,
    confined_clone_path,
    find_scope_sharing_source,
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
        # Strong refs to the best-effort local clone purges delete_scope spawns
        # (create_task results are otherwise GC-able); discarded on completion.
        self._local_purges: Set[asyncio.Task] = set()

    async def sync_scope(
        self,
        scope_id: str = None,
        scope: Scope = None,
        hinted_hash: Optional[str] = None,
        force_fetch: bool = False,
        notify_on_changes: bool = True,
        req_time: datetime.datetime = None,
        honor_backoff: bool = False,
    ):
        """Sync one scope's policy source.

        ``honor_backoff`` marks this call as pass-originated, letting the
        fetcher skip a source that keeps failing (see
        SCOPES_GIT_BACKOFF_BASE_SECONDS). It defaults to False so the explicit
        callers — POST /scopes/{id}/refresh and PUT /scopes, both of which
        arrive here through the watcher's ``trigger`` — always attempt the
        source: a customer who has just repaired credentials must not be told
        200 OK and then wait out hours or days of backoff.
        """
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

            source_id = GitPolicyFetcher.source_id(source)

            async def _scope_still_exists() -> bool:
                # Also confirms the scope still points at the source this
                # fetcher is syncing: after a repoint the old source was
                # already purged, so cloning it again would strand a dir that
                # nothing reclaims (no later purge names that source).
                try:
                    fresh = await self._scopes.get(scope.scope_id)
                except ScopeNotFoundError:
                    return False
                if not isinstance(fresh.policy, GitPolicyScopeSource):
                    return False
                return GitPolicyFetcher.source_id(fresh.policy) == source_id

            fetcher = GitPolicyFetcher(
                self._base_dir,
                scope.scope_id,
                source,
                callbacks=callbacks,
                liveness_probe=_scope_still_exists,
            )

            try:
                await fetcher.fetch_and_notify_on_changes(
                    hinted_hash=hinted_hash,
                    force_fetch=force_fetch,
                    req_time=req_time,
                    honor_backoff=honor_backoff,
                )
            except GitConcurrencyLimitExceeded as e:
                # Expected backpressure, not a fault: the zombie cap
                # (SCOPES_GIT_MAX_ZOMBIES) is refusing new git ops because too
                # many are stuck on unreachable remotes. Log it cleanly at
                # warning — a full stack trace per refused scope per pass would
                # bury the one cap-reached signal under noise during an outage.
                logger.warning(
                    "Skipping scope {scope_id} this pass: {err}",
                    scope_id=scope.scope_id,
                    err=e,
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

            deleted_source_id = GitPolicyFetcher.source_id(scope.policy)
            scope_dir = GitPolicyFetcher.repo_clone_path(self._base_dir, scope.policy)

            try:
                await self._scopes.delete(scope_id)
            finally:
                # The publish must stay reachable even when the record delete
                # raises an ambiguous outcome (committed server-side, error
                # surfaced to the client): the retry is a 204 no-op
                # (ScopeNotFoundError), so a publish gated on a clean delete
                # would orphan the purge permanently. Over-publishing
                # self-heals: the leader's sibling-check sees a still-live
                # record and keeps everything. Memory entries (all workers,
                # this one included) drop when the leader's confirmation
                # broadcast arrives.
                # FLOOR, not the primary path. The publish above is the fleet-
                # wide purge, but it is droppable at shipped defaults: a DELETE
                # usually lands on a non-leader worker (SERVER_WORKER_COUNT
                # defaults to the core count) and must traverse the broadcaster,
                # while a NON-LEADER worker only has a broadcaster reader if it
                # has a connected client or STATISTICS_ENABLED (default False).
                # (The LEADER always has one: its watcher enters a listening
                # context unconditionally — policy/watcher/task.py — so the
                # earlier claim that the leader could be deaf was backwards.)
                # A backbone outage still loses the message for everyone. If it
                # never arrives, nothing removes the dir — and on master
                # delete_scope removed it INLINE here, with no broadcast
                # involved, so without this the lost-broadcast case is a
                # regression against the merge base rather than parity with it.
                #
                # Backgrounded because DELETE's latency is bounded by contract
                # and this takes lock_source, which a sync holds across a whole
                # clone/fetch (unbounded when SCOPES_GIT_FETCH_TIMEOUT is 0).
                #
                # LOAD-BEARING ORDER: scheduled BEFORE the publish below, never
                # after it. publish() can raise a broadcaster error (see
                # LeaderScopePurger._purge_and_log), and SCOPES_PURGE_CHANNEL is
                # freeze-exempt, so during a backbone gap it is attempted and
                # fails rather than being deferred. Scheduling after it would
                # therefore skip the floor in precisely the degraded case the
                # floor exists to cover. create_task only schedules — the floor
                # cannot delay the publish or the response.
                #
                # It is a floor, not a guarantee: master serialized the record
                # delete and the sibling check under one lock, so the LAST of
                # two concurrent sibling deleters always saw no sharer. Here the
                # record delete is outside the lock, so an unlucky interleaving
                # can have both deleters see the other as still-live and both
                # skip. The leader's sibling-checked purge is the authoritative
                # path; this only guarantees that a delete reclaims at least the
                # serving pod's copy regardless of broadcaster state.
                task = asyncio.create_task(
                    self._purge_local_clone_best_effort(
                        deleted_source_id, scope_dir, scope_id
                    )
                )
                self._local_purges.add(task)
                task.add_done_callback(self._local_purges.discard)
                if self._pubsub_endpoint is not None:
                    await self._pubsub_endpoint.publish(
                        [opal_server_config.SCOPES_PURGE_CHANNEL],
                        ScopePurgeCommand(
                            source_id=deleted_source_id,
                            clone_path=str(scope_dir),
                            scope_id=scope_id,
                            reason="delete",
                        ).dict(),
                    )

    async def _purge_local_clone_best_effort(
        self, deleted_source_id: str, scope_dir: Path, scope_id: str
    ):
        """Remove THIS process's clone dir + fetcher cache entries for a
        deleted scope's source, unless a surviving scope still shares them.

        Restores the floor master had (``_purge_source_cache_if_unshared``),
        with two changes master did not have:

        - the store read is bounded by SCOPES_STORE_READ_TIMEOUT, because it is
          taken under ``lock_source`` and the Redis client has no socket timeout;
        - the removal is skipped while a git op is in flight for the source.
          Master freed the handle unconditionally; freeing one a lingering
          timed-out pygit2 call still holds on a pool thread is the
          use-after-free class 89e090be fixed. NOTHING else owns that case:
          the leader does no disk work and the deferred retry was cut, so a
          delete whose remote is hung leaves the dir until PER-15612.
        """
        # Every other destructive path in this series derives its target from
        # source_id via confined_clone_path and refuses a malformed id; this one
        # took the caller's Path. It is not wire-controlled (it comes from the
        # stored record, not a pub/sub message), so this is consistency rather
        # than a live hole — but "the one rmtree that skips the check" is not a
        # sentence worth leaving in a series about unsafe deletes.
        safe_path = confined_clone_path(self._base_dir, deleted_source_id)
        if safe_path is None or safe_path != str(scope_dir):
            logger.warning(
                f"Skipping the local clone purge for scope {scope_id}: derived "
                f"path {safe_path!r} does not match {str(scope_dir)!r}"
            )
            return
        try:
            async with GitPolicyFetcher.lock_source(deleted_source_id):
                # I4: drain the entry lock_source minted on every exit that
                # abandons this source — the early returns below included, which
                # previously leaked one each. NOT on the live-sibling path: that
                # source is still in use, and the bed asserts the entry survives
                # a sibling delete. Same rule and same lock-identity guard as
                # LeaderScopePurger.purge_source_if_unshared.
                minted = GitPolicyFetcher.repo_locks.get(deleted_source_id)
                try:
                    try:
                        timeout = opal_server_config.SCOPES_STORE_READ_TIMEOUT
                        check = find_scope_sharing_source(
                            self._scopes, deleted_source_id
                        )
                        sharer = await (
                            asyncio.wait_for(check, timeout=timeout)
                            if timeout > 0
                            else check
                        )
                    except Exception as e:
                        # KEEP the clone, unlike master. Master purged defensively
                        # on any scan failure, reasoning that over-purging
                        # self-heals. It does not self-heal cheaply here: if a
                        # sibling scope does share this source, deleting its clone
                        # takes a LIVE tenant's policy offline until the re-clone
                        # completes — and the trigger is a transient store blip.
                        # The cost of keeping is an orphan dir (PER-15612): disk
                        # against availability, and this is a best-effort floor,
                        # so it takes the conservative branch when it cannot tell.
                        logger.warning(
                            f"Local sibling check for {deleted_source_id} failed "
                            f"after deleting scope {scope_id}; keeping this "
                            f"worker's clone (it stays until PER-15612's sweep "
                            f"lands): {e!r}"
                        )
                        return
                    if sharer is not None:
                        logger.info(
                            f"Scope {sharer} still shares source "
                            f"{deleted_source_id}, keeping this worker's clone"
                        )
                        minted = None  # live source — leave its lock alone
                        return
                    if git_op_in_flight(deleted_source_id):
                        logger.info(
                            f"Skipping the local clone purge for "
                            f"{deleted_source_id}: a git operation is still in "
                            "flight; the dir stays until PER-15612's sweep lands"
                        )
                        return
                    GitPolicyFetcher.forget_repo(safe_path)
                    GitPolicyFetcher.repos_last_fetched.pop(deleted_source_id, None)
                    # Same reason as repos_last_fetched: no live scope on this
                    # worker points at the source any more, so an entry kept
                    # here is counted in the sources_in_backoff gauge for the
                    # life of the process — and would suppress the first sync
                    # of a scope later re-created against the same URL, on the
                    # strength of a deleted scope's failure history.
                    GitPolicyFetcher.forget_source_backoff(deleted_source_id)
                    try:
                        await run_sync(shutil.rmtree, safe_path)
                    except FileNotFoundError:
                        pass  # never cloned (or already gone) — nothing to clean
                    except OSError as e:
                        logger.warning(
                            f"Failed to remove clone dir {safe_path} of deleted "
                            f"scope {scope_id}: {e!r}"
                        )
                finally:
                    if (
                        minted is not None
                        and GitPolicyFetcher.repo_locks.get(deleted_source_id) is minted
                    ):
                        # Popped while the lock is held: lock_source waiters
                        # re-check the dict entry after acquiring and retry on the
                        # freshly-minted lock.
                        GitPolicyFetcher.repo_locks.pop(deleted_source_id, None)
        except Exception:
            # Detached background task: without this an unexpected failure
            # surfaces only as asyncio's unretrieved-exception noise.
            logger.exception(
                f"Best-effort local clone purge for source {deleted_source_id} "
                f"(scope {scope_id}) failed"
            )

    async def stop(self) -> None:
        """Await the best-effort local clone purges delete_scope spawned.

        Without this a DELETE that returns 204 and is followed by SIGTERM loses
        its floor: the task is detached, nothing else references it, and the
        clone dir it was about to remove survives with nothing left to reclaim
        it (no reconciliation in this PR — PER-15612).

        Best-effort and expected to be bounded by the caller: each task takes
        lock_source, which a sync can hold across a whole clone/fetch. The
        watcher calls this after cancelling its tasks and under a wait_for, the
        same discipline LeaderScopePurger.stop() already gets.
        """
        if self._local_purges:
            await asyncio.gather(*list(self._local_purges), return_exceptions=True)

    async def sync_scopes(
        self, only_poll_updates=False, notify_on_changes=True, honor_backoff=True
    ):
        """Sync every scope, in two phases.

        ``honor_backoff`` defaults to True because a whole-fleet pass is what
        the per-source backoff exists for: the periodic poll and the pre-fork
        boot preload both land here, and both re-attempt every source they
        know about. Honouring it in BOTH phases is what collapses the
        duplicate storm — phase 2 visits every scope that merely reuses a
        source, and for a source with no local clone each of those goes
        straight to a clone of its own, so one dead repo shared by N scopes
        costs N attempts per pass without it.

        The refresh-all endpoint passes False: see ScopesPolicyWatcherTask.
        """
        with tracer.trace("scopes_service.sync_scopes"):
            scopes = await self._scopes.all()
            # Emitted before the poll-updates filter below, so this is always the
            # true total rather than flapping with the caller's filter.
            metrics.gauge("opal_server.scopes.count", len(scopes))
            # Once per pass as well as on transitions: a DogStatsD gauge is
            # NO DATA between sends, and the steady state the backoff creates
            # (dead sources parked for the cap) has almost no transitions.
            emit_sources_in_backoff()
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

            # Phase 1 clones/fetches every distinct repo; phase 2 then checks the
            # duplicates against those now-present repos.
            #
            # The two phases have different cost profiles, so they get separate
            # bounds. Phase 1 does the network clone/fetch, so it is capped at
            # SCOPES_GIT_MAX_WORKERS: one unreachable repo then only stalls its
            # own slot (for the fetch timeout), not the whole pass.
            git_semaphore = asyncio.Semaphore(
                max(1, opal_server_config.SCOPES_GIT_MAX_WORKERS)
            )
            await self._sync_scopes_concurrently(
                unique_scopes,
                git_semaphore,
                force_fetch=True,
                notify_on_changes=notify_on_changes,
                honor_backoff=honor_backoff,
            )

            # Phase 2 is local-only in the common case: the repos were just
            # handled in phase 1, so _should_fetch returns False and no network
            # fetch happens (only a disk open + change-check + notify).
            # It shares the loop's default executor (the same pool that serves
            # policy bundles), so bound it by the SAME SCOPES_GIT_MAX_WORKERS
            # knob as phase 1 rather than a hard-coded floor: an operator who
            # lowers the knob to protect a small pod must be able to lower phase
            # 2 too, and over-subscribing that ~min(32, cpu+4)-thread pool only
            # queues work and contends with bundle serving. (The earlier
            # max(..., 32) made 32 a floor the knob could never reduce below.)
            local_concurrency = max(1, opal_server_config.SCOPES_GIT_MAX_WORKERS)
            local_semaphore = asyncio.Semaphore(local_concurrency)
            await self._sync_scopes_concurrently(
                duplicate_scopes,
                local_semaphore,
                force_fetch=False,
                notify_on_changes=notify_on_changes,
                honor_backoff=honor_backoff,
            )

    async def _sync_scopes_concurrently(
        self, scopes, semaphore, *, force_fetch, notify_on_changes, honor_backoff=False
    ):
        """Sync ``scopes`` concurrently, bounded by ``semaphore``.

        Each scope's failure is logged and isolated so one bad repo
        never fails the whole pass.

        Passes scope_id (not the snapshot object) so sync_scope re-gets
        fresh state right before use — a delete that landed after the
        snapshot surfaces as ScopeNotFoundError instead of re-cloning a
        dead scope's repo and re-populating the fetcher caches for it.
        """

        async def _sync_one(scope):
            async with semaphore:
                try:
                    await self.sync_scope(
                        scope_id=scope.scope_id,
                        force_fetch=force_fetch,
                        notify_on_changes=notify_on_changes,
                        honor_backoff=honor_backoff,
                    )
                except ScopeNotFoundError:
                    logger.info(
                        f"scope {scope.scope_id} was deleted while sync was queued, skipping"
                    )
                except Exception:
                    logger.exception(f"sync_scope failed for {scope.scope_id}")

        await asyncio.gather(*(_sync_one(scope) for scope in scopes))
