from pathlib import Path
from typing import List

from opal_server.redis import RedisDB
from opal_server.scopes.pull_engine import CeleryPullEngine
from opal_common.schemas.scopes import Scope


class ScopeNotFound(Exception):
    pass


class ScopeStore:
    PREFIX = 'io.permit.scope'

    def __init__(self, base_dir: str, redis: RedisDB):
        self._base_dir = base_dir
        self._redis = redis
        self._puller = CeleryPullEngine()

    async def all_scopes(self) -> List[Scope]:
        scopes = []

        for value in self._redis.scan(f'{self.PREFIX}:*'):
            scope = Scope.parse_raw(value)
            scopes.append(scope)

        return scopes

    async def get_scope(self, scope_id: str) -> Scope:
        value = await self._redis.get(self._redis_key(scope_id))

        if value:
            return Scope.parse_raw(value)
        else:
            raise ScopeNotFound()

    async def add_scope(self, scope: Scope) -> Scope:
        await self._redis.set(
            self._redis_key(scope.scope_id),
            scope
        )

        self._puller.fetch_source(Path(self._base_dir), scope)

        return scope

    async def delete_scope(self, scope_id: str):
        await self._redis.delete(self._redis_key(scope_id))

    def _redis_key(self, scope_id: str):
        return f'{self.PREFIX}:{scope_id}'


class ReadOnlyScopeStore(Exception):
    pass
