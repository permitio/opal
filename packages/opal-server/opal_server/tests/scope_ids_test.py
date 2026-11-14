"""GET /scopes/ids: the id of every stored scope, read from the store's keys
alone.

GET /scopes reads and serializes every record. The ids come from a SCAN
of the scope keys, with no read of a record, and are the ids GET /scopes
returns.
"""

import fnmatch
from typing import Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.redis_utils import RedisDB
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError, ScopeRepository

pytestmark = pytest.mark.fetch_backend("cli")


class _Redis:
    """The redis.asyncio client calls a ScopeRepository makes, on a dict.

    SCAN answers ``page`` keys per call, in insertion order, and repeats
    the last key of each page at the start of the next, as Redis may
    return a key more than once.
    """

    def __init__(self, page: int = 3) -> None:
        self.values: Dict[bytes, bytes] = {}
        self.page = page
        self.gets: List[bytes] = []
        self.scan_counts: List[Optional[int]] = []

    async def scan(self, cursor, match=None, count=None):
        self.scan_counts.append(count)
        start = int(cursor)
        keys = list(self.values)
        page = keys[max(start - 1, 0) : start + self.page]
        following = start + self.page
        if following >= len(keys):
            following = 0
        pattern = match.decode() if isinstance(match, bytes) else match
        return following, [k for k in page if fnmatch.fnmatchcase(k.decode(), pattern)]

    async def get(self, key):
        key = key.encode() if isinstance(key, str) else key
        self.gets.append(key)
        return self.values.get(key)

    def pipeline(self, transaction=True):
        return _Pipeline(self)

    async def set(self, key, value, **kwargs):
        self.values[key.encode()] = value.encode()


class _Pipeline:
    def __init__(self, redis: _Redis) -> None:
        self._redis = redis
        self._keys: List[bytes] = []

    async def __aenter__(self) -> "_Pipeline":
        return self

    async def __aexit__(self, *exc) -> None:
        pass

    def get(self, key) -> "_Pipeline":
        self._keys.append(key)
        return self

    async def execute(self) -> List[Optional[bytes]]:
        return [await self._redis.get(key) for key in self._keys]


def _scope(scope_id: str) -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url="https://git.example.test/policy.git",
            branch="main",
            auth=NoAuthData(),
        ),
    )


def _repository(redis: _Redis) -> ScopeRepository:
    db = RedisDB("redis://localhost:1")
    db._redis = redis
    return ScopeRepository(db)


@pytest.mark.asyncio
async def test_the_ids_are_the_ids_of_every_stored_scope():
    redis = _Redis()
    repository = _repository(redis)
    for scope_id in ["b", "a", "env:with:colons", "d", "c", "default", "e"]:
        await repository.put(_scope(scope_id))
    redis.values[b"another/Prefix:x"] = b"{}"
    redis.values[b"permit.io/Scopes:y"] = b"{}"

    ids = await repository.ids()

    assert ids == sorted({s.scope_id for s in await repository.all()})
    assert ids == ["a", "b", "c", "d", "default", "e", "env:with:colons"]


@pytest.mark.asyncio
async def test_the_ids_read_no_record():
    redis = _Redis()
    repository = _repository(redis)
    for scope_id in ["a", "b", "c", "d"]:
        await repository.put(_scope(scope_id))

    await repository.ids()

    assert redis.gets == []
    assert set(redis.scan_counts) == {1000}


@pytest.mark.asyncio
async def test_no_stored_scope_has_no_ids():
    assert await _repository(_Redis()).ids() == []


class _Scopes:
    def __init__(self, ids):
        self._ids = ids
        self.reads = 0

    async def ids(self):
        return list(self._ids)

    async def all(self):
        self.reads += 1
        return [_scope(scope_id) for scope_id in self._ids]

    async def get(self, scope_id):
        self.reads += 1
        if scope_id not in self._ids:
            raise ScopeNotFoundError(scope_id)
        return _scope(scope_id)


class _Authenticator:
    def __init__(self, claims=None):
        self.enabled = claims is not None
        self._claims = claims or {}

    def __call__(self):
        return self._claims


def _client(scopes, authenticator=None):
    app = FastAPI()
    app.include_router(
        init_scope_router(scopes, authenticator or _Authenticator(), None, None),
        prefix="/scopes",
    )
    return TestClient(app)


def test_the_route_answers_the_ids():
    scopes = _Scopes(["a", "b", "ids"])

    response = _client(scopes).get("/scopes/ids")

    assert response.status_code == 200
    assert response.json() == ["a", "b", "ids"]
    assert scopes.reads == 0


def test_the_route_leaves_the_scope_routes_alone():
    client = _client(_Scopes(["a"]))

    assert client.get("/scopes/a").json()["scope_id"] == "a"
    assert client.get("/scopes/missing").status_code == 404


@pytest.mark.parametrize(
    "claims, status",
    [({"peer_type": "datasource"}, 200), ({"peer_type": "client"}, 401)],
    ids=["datasource", "client"],
)
def test_the_route_answers_a_datasource_only(claims, status):
    response = _client(_Scopes(["a"]), _Authenticator(claims)).get("/scopes/ids")

    assert response.status_code == status
