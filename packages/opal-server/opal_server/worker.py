from celery import Celery
from asgiref.sync import async_to_sync, AsyncToSync

from opal_server.config import opal_server_config
from opal_server.redis import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository


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
    f = AsyncToSync(worker.sync_scope)
    f(scope_id)
