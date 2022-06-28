import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, cast

import git
from aiohttp import ClientSession
from asgiref.sync import async_to_sync
from celery import Celery
from opal_client.config import opal_client_config
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.policy.watcher.callbacks import create_policy_update
from opal_server.redis import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository


class Worker:
    def __init__(self, base_dir: Path, scopes: ScopeRepository):
        self._base_dir = base_dir
        self._scopes = scopes
        self._http: Optional[ClientSession] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self):
        self._http = ClientSession()

    async def stop(self):
        await self._http.close()

    async def sync_scope(self, scope_id: str):
        scope = await self._scopes.get(scope_id)

        fetcher = None

        if isinstance(scope.policy, GitPolicyScopeSource):
            source = cast(GitPolicyScopeSource, scope.policy)
            scope_dir = self._base_dir / "scopes" / scope_id

            async def on_update(old_revision: str, new_revision: str):
                if old_revision == new_revision:
                    return

                repo = git.Repo(scope_dir)
                notification = await create_policy_update(
                    repo.commit(old_revision),
                    repo.commit(new_revision),
                    source.extensions,
                )

                url = f"{opal_client_config.SERVER_URL}/scopes/{scope_id}/policy_update"

                async with self._http.post(url, json=notification.dict()):
                    pass

            fetcher = GitPolicyFetcher(
                self._base_dir,
                scope_id,
                source,
                callbacks=SimpleNamespace(on_update=on_update),
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


def create_worker() -> Worker:
    opal_base_dir = Path(opal_server_config.BASE_DIR)
    worker = Worker(
        base_dir=opal_base_dir,
        scopes=ScopeRepository(RedisDB(opal_server_config.REDIS_URL)),
    )

    return worker


def with_worker(f):
    async def _inner(*args, **kwargs):
        async with create_worker() as worker:
            await f(worker, *args, **kwargs)

    return _inner


app = Celery(
    "opal-worker",
    broker=opal_server_config.REDIS_URL,
    backend=opal_server_config.REDIS_URL,
)
app.conf.task_default_queue = "opal-worker"


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        opal_server_config.POLICY_REFRESH_INTERVAL, periodic_check.s()
    )


@app.task
def sync_scope(scope_id: str):
    return async_to_sync(with_worker(Worker.sync_scope))(scope_id)


@app.task
def delete_scope(scope_id: str):
    return async_to_sync(with_worker(Worker.delete_scope))(scope_id)


@app.task
def periodic_check():
    return async_to_sync(with_worker(Worker.periodic_check))()
