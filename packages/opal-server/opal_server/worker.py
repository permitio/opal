"""
OPAL background worker process
"""
import asyncio
import os
import json

from celery import Celery

from opal_server.policy.watcher.callbacks import publish_changed_directories
from opal_server.publisher import setup_publisher_task
from opal_server.redis import RedisDB
from opal_server.scopes.pullers import create_puller
from opal_server.scopes.scope_store import Scope, ScopeStore
from opal_server.config import opal_server_config

app = Celery('opal-worker',
             broker=opal_server_config.REDIS_URL,
             backend=opal_server_config.REDIS_URL)


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        opal_server_config.POLICY_REPO_POLLING_INTERVAL,
        periodic_check.s()
    )


@app.task
def fetch_source(base_dir: str, scope_json: str):
    scope = Scope.parse_obj(json.loads(scope_json))
    puller = create_puller(base_dir, scope)

    puller.pull()


@app.task
def periodic_check():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_periodic_check_sync())


async def _periodic_check_sync():
    base_dir = os.path.join(opal_server_config.BASE_DIR, "scopes")
    scope_store = ScopeStore(
        base_dir=base_dir,
        redis=RedisDB(opal_server_config.REDIS_URL)
    )

    scopes = await scope_store.all_scopes()

    for scope_id, scope in scopes:
        if not scope.policy.polling:
            continue

        puller = create_puller(base_dir, scope)

        if puller.check():
            old_commit, new_commit = puller.diff()
            puller.pull()

            publisher = setup_publisher_task(
                server_uri=opal_server_config.OPAL_WS_LOCAL_URL,
                server_token=opal_server_config.OPAL_WS_TOKEN,
                prefix=scope.scope_id)

            await publish_changed_directories(
                old_commit=old_commit, new_commit=new_commit,
                publisher=publisher
            )
