import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, cast

import git
from aiohttp import ClientSession
from asgiref.sync import async_to_sync
from celery import Celery
from opal_common.logger import configure_logs, logger
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.utils import get_authorization_header, tuple_to_dict
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
        logger.info(f"Sync scope: {scope_id}")
        scope = await self._scopes.get(scope_id)

        fetcher = None

        if isinstance(scope.policy, GitPolicyScopeSource):
            source = cast(GitPolicyScopeSource, scope.policy)
            scope_dir = self._base_dir / "scopes" / scope_id

            async def on_update(old_revision: str, new_revision: str):
                if old_revision == new_revision:
                    logger.info(
                        f"scope '{scope_id}': No new commits, HEAD is at '{new_revision}'"
                    )
                    return

                logger.info(
                    f"scope '{scope_id}': Found new commits: old HEAD was '{old_revision}', new HEAD is '{new_revision}'"
                )
                repo = git.Repo(scope_dir)
                notification = await create_policy_update(
                    repo.commit(old_revision),
                    repo.commit(new_revision),
                    source.extensions,
                )

                url = f"{opal_server_config.SERVER_URL}/scopes/{scope_id}/policy/update"

                logger.info(
                    f"Triggering policy update for scope {scope_id}: {notification.dict()}"
                )
                async with self._http.post(
                    url,
                    json=notification.dict(),
                    headers=tuple_to_dict(
                        get_authorization_header(opal_server_config.WORKER_TOKEN)
                    ),
                ):
                    pass

            logger.info(
                f"Initializing git fetcher: scope_id={scope_id} and url={source.url}"
            )
            fetcher = GitPolicyFetcher(
                self._base_dir,
                scope_id,
                source,
                callbacks=SimpleNamespace(on_update=on_update),
            )

        if fetcher:
            try:
                await fetcher.fetch()
            except Exception as e:
                logger.exception(
                    f"Could not fetch policy for scope {scope_id}, got error: {e}"
                )

    async def delete_scope(self, scope_id: str):
        scope_dir = self._base_dir / "scopes" / scope_id
        shutil.rmtree(scope_dir, ignore_errors=True)

    async def periodic_check(self):
        logger.info("Polling OPAL scopes for policy changes")
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


configure_logs()
app = Celery(
    "opal-worker",
    broker=opal_server_config.REDIS_URL,
    backend=opal_server_config.REDIS_URL,
)
app.conf.task_default_queue = "opal-worker"
app.conf.task_serializer = "json"


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    polling_interval = opal_server_config.POLICY_REFRESH_INTERVAL
    if polling_interval == 0:
        logger.info("OPAL scopes: polling task is off.")
    else:
        logger.info(
            f"OPAL scopes: started polling task, interval is {polling_interval} seconds."
        )
        sender.add_periodic_task(polling_interval, periodic_check.s())


@app.task
def sync_scope(scope_id: str):
    return async_to_sync(with_worker(Worker.sync_scope))(scope_id)


@app.task
def delete_scope(scope_id: str):
    return async_to_sync(with_worker(Worker.delete_scope))(scope_id)


@app.task
def periodic_check():
    return async_to_sync(with_worker(Worker.periodic_check))()
