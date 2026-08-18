import asyncio
import datetime
from pathlib import Path
from typing import Any

from fastapi_websocket_pubsub import Topic
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    drain_git_ops,
    git_busy_count,
    shutdown_git_executor,
)
from opal_server.policy.watcher.task import BasePolicyWatcherTask
from opal_server.redis_utils import RedisDB
from opal_server.scopes.purge import LeaderScopePurger
from opal_server.scopes.scope_repository import ScopeRepository
from opal_server.scopes.service import ScopesService

# Upper bound on the shutdown drain of in-flight scope purges. The drain is
# best-effort: a purge's rmtree runs on a worker thread and completes whether or
# not we are still awaiting it. What is abandoned before it starts is NOT
# recovered — no reconciliation sweep exists in this PR (split out, PER-15612),
# and no later purge will name a deleted scope's source. Blocking shutdown
# longer would be strictly worse —
# stop() runs while the leadership lock is still held, so no other worker can
# take over, and k8s's terminationGracePeriodSeconds (30s by default) would
# SIGKILL us anyway.
_PURGE_DRAIN_TIMEOUT = 5.0


class ScopesPolicyWatcherTask(BasePolicyWatcherTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set in start(); None means "nothing to unsubscribe" (stop() without a
        # successful start, or a second stop()).
        self._purger_sub_id = None

        self._scopes = ScopeRepository(RedisDB(opal_server_config.REDIS_URL))
        self._service = ScopesService(
            base_dir=Path(opal_server_config.BASE_DIR),
            scopes=self._scopes,
            pubsub_endpoint=self._pubsub_endpoint,
        )
        self._purger = LeaderScopePurger(
            base_dir=Path(opal_server_config.BASE_DIR),
            scopes=self._scopes,
            pubsub_endpoint=self._pubsub_endpoint,
        )

    async def start(self):
        await super().start()
        # Leader-only purge authorization: this task starts only on the leader, so
        # registering here (not at worker boot) preserves the invariant that
        # the leader is the only mutator on sync paths (see the note in
        # scopes/purge.py — a delete also removes on the serving worker).
        #
        # Registered under a DEDICATED subscriber id rather than through
        # PubSubEndpoint.subscribe, which files every server-side subscription
        # under one shared endpoint id: EventNotifier.unsubscribe deletes that
        # id's WHOLE callback list for the topic, so unsubscribing by topic in
        # stop() would also drop the every-worker handle_purge_message
        # subscription (registered once at boot in server.py, never re-added) —
        # leaving this process deaf to fleet purges for the rest of its life.
        # Our own id makes the leader subscription independently removable.
        self._purger_sub_id = self._pubsub_endpoint.notifier.gen_subscriber_id()
        await self._pubsub_endpoint.notifier.subscribe(
            self._purger_sub_id,
            [opal_server_config.SCOPES_PURGE_CHANNEL],
            self._purger.handle,
        )
        # With POLICY_REFRESH_INTERVAL <= 0 this boot sync is the ONLY
        # pass-originated sync this process ever runs, so a source that failed
        # transiently during the pre-fork preload (whose entry survives
        # reset_caches on purpose) must not be inherited — it would never be
        # attempted again. Clearing the inherited entries (rather than not
        # honouring the backoff) keeps the within-pass property: phase-2
        # duplicates of a source that fails in THIS pass are still collapsed
        # to one attempt.
        # Clearing the whole dict is safe here: this runs once, right after
        # this process won leadership, and a freshly forked worker cannot have
        # recorded anything of its own before that (only leaders sync).
        if opal_server_config.POLICY_REFRESH_INTERVAL <= 0:
            GitPolicyFetcher.source_backoff.clear()
        self._tasks.append(asyncio.create_task(self._sync_all()))

        if opal_server_config.POLICY_REFRESH_INTERVAL > 0:
            self._tasks.append(asyncio.create_task(self._periodic_polling()))

    async def stop(self):
        # stop() runs TWICE on the normal path — once from
        # BasePolicyWatcherTask.__aexit__ (server.py's `async with self.watcher`)
        # and again from stop_server_background_tasks — so every step here is
        # idempotent: the subscriber id is consumed on first use, signal_stop and
        # the drain are no-ops once done.
        #
        # Stop accepting new purge messages first (cheap, non-blocking).
        if self._purger_sub_id is not None:
            sub_id, self._purger_sub_id = self._purger_sub_id, None
            try:
                await self._pubsub_endpoint.notifier.unsubscribe(
                    sub_id, [opal_server_config.SCOPES_PURGE_CHANNEL]
                )
            except Exception:
                logger.exception("Failed to unsubscribe scope purge handler on stop")
        self._purger.signal_stop()

        # Cancel our tasks BEFORE draining the purges, not after: a queued purge
        # first waits on GitPolicyFetcher.lock_source, which a sync task holds
        # across a clone/fetch (up to SCOPES_GIT_FETCH_TIMEOUT, and unbounded
        # when that is 0). Draining first would wait on a lock whose release
        # requires the very cancellation the drain is blocking — an unrecoverable
        # shutdown hang, taken while the leadership lock is still held.
        result = await super().stop()

        # Best-effort, bounded (see _PURGE_DRAIN_TIMEOUT).
        #
        # ONLY the purger is drained here. The DELETE floor's tasks live on the
        # ScopesService that init_scope_router received (built in server.py), NOT
        # on self._service — the watcher constructs its own, and only ever syncs
        # with it. Draining self._service gathered an empty set. This is also the
        # wrong place structurally: the watcher exists only on the leader, while
        # a DELETE usually lands on a non-leader. That drain is per-worker, on
        # OpalServer.stop_server_background_tasks.
        try:
            await asyncio.wait_for(self._purger.stop(), timeout=_PURGE_DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(
                "Abandoned in-flight scope purges at shutdown after {timeout}s; "
                "their clone dirs stay on disk until the source is purged again",
                timeout=_PURGE_DRAIN_TIMEOUT,
            )
        return result

    async def _sync_all(self, honor_backoff: bool = True):
        # sync_scopes must be wrapped: this coroutine is launched fire-and-forget
        # from start() (boot), so an unhandled raise here would die silently —
        # the exception is never retrieved (stop() gathers with
        # return_exceptions=True and discards it), not even asyncio's
        # "never retrieved" warning until GC.
        #
        # honor_backoff defaults to True for the boot call in start(): this
        # process may have been forked from a master whose preload already
        # discovered which repos are unreachable, and re-attempting all of them
        # at boot is the storm the backoff exists to prevent. trigger() passes
        # False for the operator-driven refresh-all — see there.
        try:
            await self._service.sync_scopes(honor_backoff=honor_backoff)
        except Exception:
            logger.exception("Scope sync (sync_scopes) failed")

    async def _periodic_polling(self):
        try:
            while True:
                await asyncio.sleep(opal_server_config.POLICY_REFRESH_INTERVAL)
                # Leader heartbeat. This loop runs only inside the leadership
                # lock, so `sum by env` reaching 0 means no worker holds it
                # anywhere and scope syncing has silently stopped — pods stay
                # Ready and /healthcheck stays 200 throughout.
                metrics.gauge("opal_server.scopes.leader", 1)
                logger.info("Periodic sync")
                try:
                    await self._service.sync_scopes(only_poll_updates=True)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.exception(f"Periodic sync (sync_scopes) failed")

        except asyncio.CancelledError:
            logger.info("Periodic sync cancelled")
            raise

    async def trigger(self, topic: Topic, data: Any):
        if data is not None and isinstance(data, dict):
            # Refresh single scope
            try:
                await self._service.sync_scope(
                    scope_id=data["scope_id"],
                    force_fetch=data.get("force_fetch", False),
                    hinted_hash=data.get("hinted_hash"),
                    req_time=datetime.datetime.now(),
                )
            except KeyError:
                logger.warning(
                    "Got invalid keyword args for single scope refresh: %s", data
                )
        else:
            # Refresh all scopes. This branch is reached only from something
            # asking for a sync NOW — POST /scopes/refresh (the git-provider
            # webhook publishes on this topic too, but only when
            # POLICY_REPO_URL is set, which scopes mode does not use) — so it
            # does not honour the per-source backoff: the
            # sources an operator hits this endpoint for are precisely the ones
            # they have just repaired, and answering them with a silent skip
            # makes the endpoint useless in the only situation it is used.
            await self._sync_all(honor_backoff=False)

    @staticmethod
    def preload_scopes():
        """Clone all scopes repositories as part as server startup.

        This speeds up the first sync of scopes after workers are
        started.
        """
        if opal_server_config.SCOPES:
            logger.info("Preloading repo clones for scopes")

            service = ScopesService(
                base_dir=Path(opal_server_config.BASE_DIR),
                scopes=ScopeRepository(RedisDB(opal_server_config.REDIS_URL)),
                pubsub_endpoint=None,
            )
            asyncio.run(service.sync_scopes(notify_on_changes=False))

            # Bounded window for a just-finished clone/fetch to clear its in-flight
            # marker before teardown+fork. Ops still lingering (hung remote) are
            # left running; reset_caches's guard then skips freeing their handles.
            # A False return means the drain timed out with git ops STILL running:
            # those threads persist in the master across the fork, so a forked
            # worker can race them on the shared clone dir. Log it — this is the
            # one condition that carries that risk, and it must not be silent.
            drained = drain_git_ops(opal_server_config.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT)
            if not drained:
                logger.warning(
                    "Preload drain timed out ({timeout}s) with git ops still "
                    "in flight ({in_flight}); they persist in the master across "
                    "fork. Consider raising SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT or "
                    "lowering SCOPES_GIT_FETCH_TIMEOUT.",
                    timeout=opal_server_config.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT,
                    in_flight=git_busy_count(),
                )

            # Clear git-op bookkeeping built during preload (in-flight markers
            # and the loop-bound live-op semaphore) so the gunicorn master does
            # not carry stale state into forked workers. Git ops run on per-op
            # daemon threads; there is no shared pool to tear down.
            shutdown_git_executor()

            # Drop every cached repo handle/lock/timestamp built during preload
            # so none of it is inherited by forked workers. Sync (the only path
            # that populates these caches) is leader-only, so a non-leader worker
            # that inherited a handle could never purge it — the fleet-wide purge
            # broadcast reaches a worker only when its broadcaster reader runs
            # (STATISTICS_ENABLED or a connected client), leaving a client-less
            # non-leader to pin the handle for life. The on-disk clones remain;
            # workers re-open handles lazily.
            GitPolicyFetcher.reset_caches()

            logger.warning("Finished preloading repo clones for scopes.")
