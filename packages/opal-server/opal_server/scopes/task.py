import asyncio
import datetime
from pathlib import Path
from typing import Any

from fastapi_websocket_pubsub import Topic
from opal_common.logger import logger
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


class ScopesPolicyWatcherTask(BasePolicyWatcherTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        # Leader-only disk purge: this task starts only on the leader, so
        # registering here (not at worker boot) preserves the invariant that
        # only the leader mutates the clone tree.
        await self._pubsub_endpoint.subscribe(
            [opal_server_config.SCOPES_PURGE_CHANNEL], self._purger.handle
        )
        self._tasks.append(asyncio.create_task(self._sync_all_then_sweep()))

        polling_on = opal_server_config.POLICY_REFRESH_INTERVAL > 0
        if polling_on:
            self._tasks.append(asyncio.create_task(self._periodic_polling()))

        # Always-on orphan-sweep backstop — but skip it when polling is on,
        # because _periodic_polling already sweeps after every poll. Running
        # both would double the disk scans and emit duplicate confirmed-orphan
        # purge broadcasts. In prod POLICY_REFRESH_INTERVAL is 0, so this timer
        # is the sole sweeper there.
        if opal_server_config.SCOPES_ORPHAN_SWEEP_INTERVAL > 0 and not polling_on:
            self._tasks.append(asyncio.create_task(self._periodic_orphan_sweep()))

    async def stop(self):
        return await super().stop()

    async def _sync_all_then_sweep(self):
        await self._service.sync_scopes()
        # After sync, disk state is settled: anything on disk that no live
        # scope references is an orphan (crash leftovers, redis-wiped boot,
        # old-shard dirs after a SCOPES_REPO_CLONES_SHARDS change).
        # Runs on boot and on refresh-all triggers.
        try:
            await self._purger.sweep_orphans()
        except Exception:
            # The backstop must never kill the watcher task or fail silently;
            # the periodic pass retries (and logs) on its own schedule.
            logger.exception("Orphan sweep failed")

    async def _periodic_polling(self):
        try:
            while True:
                await asyncio.sleep(opal_server_config.POLICY_REFRESH_INTERVAL)
                logger.info("Periodic sync")
                try:
                    await self._service.sync_scopes(only_poll_updates=True)
                    await self._purger.sweep_orphans()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.exception(f"Periodic sync (sync_scopes) failed")

        except asyncio.CancelledError:
            logger.info("Periodic sync cancelled")
            raise

    async def _periodic_orphan_sweep(self):
        """Always-on backstop independent of POLICY_REFRESH_INTERVAL. _periodic_polling
        also sweeps but only runs when polling is enabled; with it off, boot's
        _sync_all_then_sweep was the sole sweep, so a delete/repoint whose purge
        broadcast never reached the leader leaked until refresh-all."""
        try:
            while True:
                await asyncio.sleep(opal_server_config.SCOPES_ORPHAN_SWEEP_INTERVAL)
                try:
                    await self._purger.sweep_orphans()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Periodic orphan sweep failed")
        except asyncio.CancelledError:
            logger.info("Periodic orphan sweep cancelled")
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
            # Refresh all scopes
            await self._sync_all_then_sweep()

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
            drained = drain_git_ops(
                opal_server_config.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT
            )
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
