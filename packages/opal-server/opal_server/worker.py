import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import git
from aiohttp import ClientSession
from asgiref.sync import async_to_sync
from celery import Celery
from fastapi_websocket_pubsub import PubSubClient
from opal_client.config import opal_client_config
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.utils import get_authorization_header
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.policy.watcher.callbacks import create_policy_update
from opal_server.redis import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository


class Worker:
    def __init__(
        self, base_dir: Path, scopes: ScopeRepository, pubsub_client: PubSubClient
    ):
        self._base_dir = base_dir
        self._scopes = scopes
        self._pubsub_client = pubsub_client

    async def sync_scope(self, scope_id: str):
        scope = await self._scopes.get(scope_id)

        fetcher = None

        if isinstance(scope.policy, GitPolicyScopeSource):
            source = cast(GitPolicyScopeSource, scope.policy)
            scope_dir = self._base_dir / "scopes" / scope_id

            async def on_update(old_revision: str, new_revision: str):
                # if old_revision == new_revision:
                #     return

                repo = git.Repo(scope_dir)
                notification = await create_policy_update(
                    repo.commit(old_revision),
                    repo.commit(new_revision),
                    source.extensions,
                )

                url = f"{opal_client_config.SERVER_URL}/scopes/{scope_id}/policy_update"

                async with ClientSession():
                    async with self._http_session.post(url, json=notification.dict()):
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
        pubsub_client=PubSubClient(
            server_uri=opal_client_config.SERVER_PUBSUB_URL,
            extra_headers=[get_authorization_header(opal_server_config.OPAL_WS_TOKEN)],
        ),
    )

    return worker


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
    worker = create_worker()
    return async_to_sync(worker.sync_scope)(scope_id)


@app.task
def delete_scope(scope_id: str):
    worker = create_worker()
    return async_to_sync(worker.delete_scope)(scope_id)


@app.task
def periodic_check():
    worker = create_worker()
    return async_to_sync(worker.periodic_check)()
