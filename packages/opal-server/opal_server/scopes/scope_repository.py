from typing import List

from opal_common.schemas.scopes import Scope
from opal_server.redis_utils import RedisDB


class ScopeNotFoundError(Exception):
    def __init__(self, id: str):
        self._id = id

    def __str__(self) -> str:
        return f"Scope {self._id} not found"


# SCAN's COUNT for ids(): how many keys Redis looks at per call. With 1,000,
# tens of thousands of scopes take tens of calls rather than thousands, and
# each call stays short.
_IDS_SCAN_COUNT = 1000


class ScopeRepository:
    def __init__(self, redis_db: RedisDB):
        self._redis_db = redis_db
        self._prefix = "permit.io/Scope"

    @property
    def db(self) -> RedisDB:
        return self._redis_db

    async def all(self) -> List[Scope]:
        scopes = []

        async for value in self._redis_db.scan(f"{self._prefix}:*"):
            if not value:
                # The scan lists keys and then reads each one, so a scope
                # deleted in between comes back as None. Passing that to
                # model_validate_json raises ValidationError and kills the WHOLE scan —
                # one concurrently-deleted scope would abort an entire
                # sync_scopes pass, and poison the sibling check a delete's
                # purge depends on (observed under the bed's churn: two
                # deletes' clone dirs stranded because their own delete raced
                # the scan). A key that no longer exists is simply not a scope.
                #
                # Deliberately narrow: a record that IS present but does not
                # parse still raises, because that is corruption and should not
                # be silently skipped.
                continue
            scope = Scope.model_validate_json(value)
            scopes.append(scope)

        return scopes

    async def ids(self) -> List[str]:
        """The id of every stored scope, sorted, from the names of the keys
        alone: no record is read.

        They are the ids of the scopes ``all()`` returns, read the same
        way (a SCAN of the scope keys), without reading and parsing each
        record.
        """
        prefix = f"{self._prefix}:"
        found = set()
        async for key in self._redis_db.scan_keys(f"{prefix}*", _IDS_SCAN_COUNT):
            found.add(key.decode()[len(prefix) :])
        return sorted(found)

    async def get(self, scope_id: str) -> Scope:
        key = self._redis_key(scope_id)
        value = await self._redis_db.get(key)

        if value:
            return Scope.model_validate_json(value)
        else:
            raise ScopeNotFoundError(scope_id)

    async def put(self, scope: Scope):
        key = self._redis_key(scope.scope_id)
        await self._redis_db.set(key, scope)

    async def delete(self, scope_id: str):
        key = self._redis_key(scope_id)
        await self._redis_db.delete(key)

    def _redis_key(self, scope_id: str):
        return f"{self._prefix}:{scope_id}"
