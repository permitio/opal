import asyncio
import datetime
from pathlib import Path
from typing import Any

from fastapi_websocket_pubsub import Topic
from opal_common.logger import logger
from opal_server.config import opal_server_config
from opal_server.git_fetcher import shutdown_git_executor
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
        self._tasks.append(asyncio.create_task(self._boot_sync_then_sweep()))

        if opal_server_config.POLICY_REFRESH_INTERVAL > 0:
            self._tasks.append(asyncio.create_task(self._periodic_polling()))

    async def stop(self):
        return await super().stop()

    async def _boot_sync_then_sweep(self):
        await self._service.sync_scopes()
        # After sync, disk state is settled: anything on disk that no live
        # scope references is an orphan (crash leftovers, redis-wiped boot,
        # old-shard dirs after a SCOPES_REPO_CLONES_SHARDS change).
        try:
            await self._purger.sweep_orphans()
        except Exception:
            # The backstop must never kill the watcher task or fail silently;
            # the periodic pass retries (and logs) on its own schedule.
            logger.exception("Boot-time orphan sweep failed")

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
            await self._service.sync_scopes()

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

            # Release the git pool built during preload so the gunicorn master
            # does not carry pool threads into forked workers (they would be
            # dead in the child). Workers rebuild their own pool on first use.
            shutdown_git_executor()

            logger.warning("Finished preloading repo clones for scopes.")
