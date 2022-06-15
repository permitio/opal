import asyncio
import shutil
from pathlib import Path
from typing import cast

from celery import Celery
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.redis import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository


def async_to_sync(callable, *args, **kwargs):
    loop = asyncio.get_event_loop()

    async def f():
        return await callable(*args, **kwargs)

    return loop.run_until_complete(f())


class Worker:
    def __init__(self, base_dir: Path, scopes: ScopeRepository):
        self._base_dir = base_dir
        self._scopes = scopes

    async def sync_scope(self, scope_id: str):
        scope = await self._scopes.get(scope_id)

        fetcher = None

        if isinstance(scope.policy, GitPolicyScopeSource):
            fetcher = GitPolicyFetcher(
                self._base_dir, scope_id, cast(GitPolicyScopeSource, scope.policy)
            )

        if fetcher:
            await fetcher.fetch()

    async def delete_scope(self, scope_id: str):
        scope_dir = self._base_dir / "scopes" / scope_id
        shutil.rmtree(scope_dir, ignore_errors=True)

    async def periodic_check(self):
        scopes = await self._scopes.all()

        for scope in scopes:
            if scope.policy.poll_updates:
                sync_scope.delay(scope.scope_id)


opal_base_dir = Path(opal_server_config.BASE_DIR)
worker = Worker(
    base_dir=opal_base_dir,
    scopes=ScopeRepository(RedisDB(opal_server_config.REDIS_URL)),
)
app = Celery(
    "opal-worker",
    broker=opal_server_config.REDIS_URL,
    backend=opal_server_config.REDIS_URL,
)


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        opal_server_config.POLICY_REFRESH_INTERVAL, periodic_check.s()
    )


@app.task
def sync_scope(scope_id: str):
    return async_to_sync(worker.sync_scope, scope_id)


@app.task
def delete_scope(scope_id: str):
    return async_to_sync(worker.delete_scope, scope_id)


@app.task
def periodic_check():
    return async_to_sync(worker.periodic_check)
