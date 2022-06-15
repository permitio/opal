from uuid import UUID

from opal_common.schemas.scopes import Scope
from opal_server.redis import RedisDB


class ScopeNotFoundError(Exception):
    def __init__(self, id: str):
        self._id = id

    def __str__(self) -> str:
        return f"Scope {self._id} not found"


class ScopeRepository:
    def __init__(self, redis_db: RedisDB):
        self._redis_db = redis_db

    async def get(self, scope_id: str) -> Scope:
        key = self._redis_key(scope_id)
        value = await self._redis_db.get(key)

        if value:
            return Scope.parse_raw(value)
        else:
            raise ScopeNotFoundError(scope_id)

    async def put(self, scope: Scope):
        key = self._redis_key(scope.scope_id)
        await self._redis_db.set(key, scope)

    def _redis_key(self, scope_id: str):
        return f"permit.io/Scope:{scope_id}"
