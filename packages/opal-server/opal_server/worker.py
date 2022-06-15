import asyncio

from celery import Celery

from opal_server.config import opal_server_config
from opal_server.redis import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository


def async_to_sync(callable, *args, **kwargs):
    loop = asyncio.get_event_loop()

    async def f():
        return await callable(*args, **kwargs)

    return loop.run_until_complete(f())


class Worker:
    def __init__(self, scopes: ScopeRepository):
        self._scopes = scopes

    async def sync_scope(self, scope_id: str):
        scope = await self._scopes.get(scope_id)


worker = Worker(
    scopes=ScopeRepository(RedisDB(opal_server_config.REDIS_URL))
)
app = Celery("opal-worker", broker=opal_server_config.REDIS_URL)


@app.task
def sync_scope(scope_id: str):
    return async_to_sync(worker.sync_scope, scope_id)
