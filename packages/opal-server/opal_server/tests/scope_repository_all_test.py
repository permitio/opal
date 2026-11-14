"""ScopeRepository.all: every stored scope, read in a few round trips of
single-key commands, and parsed off the event loop.

A sync pass starts with it. Read a key at a time, each scope cost a
round trip, and every record was parsed on the loop. SCAN pages of 1,000
keys are read with one pipeline of GETs each (an MGET would span hash
slots, which a Redis in cluster mode refuses), and the records are
parsed on a thread.
"""

import asyncio
import fnmatch
import time
from typing import Dict, List, Optional

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server import redis_utils
from opal_server.redis_utils import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository
from pydantic import ValidationError
from redis.exceptions import ResponseError

# How long one record takes to parse in the slow-parse test (a stand-in for
# thousands of records), and the most the loop may lag meanwhile.
PARSE_SECONDS = 0.01
MAX_LAG_SECONDS = 0.1


class _Pipeline:
    def __init__(self, redis: "_Redis") -> None:
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
        self._redis.calls.append(f"PIPELINE {len(self._keys)} GET")
        return [self._redis.values.get(key) for key in self._keys]


class _Redis:
    """The redis.asyncio client calls RedisDB.scan makes, on a dict, counting
    the round trips, as a Redis in cluster mode answers them: a command on keys
    of more than one hash slot is refused (CROSSSLOT).

    SCAN answers COUNT keys per call (10 when none is given, as Redis
    roughly does), in insertion order, the keys that do not match left
    out.
    """

    def __init__(self) -> None:
        self.values: Dict[bytes, Optional[bytes]] = {}
        self.calls: List[str] = []

    async def scan(self, cursor, match=None, count=None):
        page = count or 10
        self.calls.append(f"SCAN {page}")
        start = int(cursor)
        keys = list(self.values)
        following = start + page
        if following >= len(keys):
            following = 0
        found = keys[start : start + page]
        return following, [k for k in found if fnmatch.fnmatchcase(k.decode(), match)]

    async def get(self, key):
        self.calls.append("GET")
        return self.values.get(key)

    def pipeline(self, transaction=True):
        assert transaction is False, "a MULTI of keys in many slots is refused too"
        return _Pipeline(self)

    async def mget(self, keys):
        if len(keys) > 1:
            raise ResponseError("CROSSSLOT Keys in request don't hash to the same slot")
        return [self.values.get(key) for key in keys]


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


def _stored(redis: _Redis, scope_ids) -> ScopeRepository:
    for scope_id in scope_ids:
        key = f"permit.io/Scope:{scope_id}".encode()
        redis.values[key] = _scope(scope_id).model_dump_json().encode()
    db = RedisDB("redis://localhost:1")
    db._redis = redis
    return ScopeRepository(db)


@pytest.mark.asyncio
async def test_every_stored_scope_is_read_one_pipeline_per_page_of_1000():
    """Mutation: an MGET per page (refused across slots), a GET per key, or
    SCAN's default COUNT fails here."""
    redis = _Redis()
    ids = [f"s{i:04d}" for i in range(2500)]
    repository = _stored(redis, ids)

    scopes = await repository.all()

    assert sorted(s.scope_id for s in scopes) == ids
    assert redis_utils._SCAN_COUNT == 1000
    assert redis.calls == [
        "SCAN 1000",
        "PIPELINE 1000 GET",
        "SCAN 1000",
        "PIPELINE 1000 GET",
        "SCAN 1000",
        "PIPELINE 500 GET",
    ]


@pytest.mark.asyncio
async def test_a_page_with_no_scope_key_sends_no_read():
    """SCAN may answer a page with no key that matches: nothing is read for
    it."""
    redis = _Redis()
    for i in range(1000):
        redis.values[f"other:{i}".encode()] = b"{}"
    repository = _stored(redis, ["a"])

    scopes = await repository.all()

    assert [s.scope_id for s in scopes] == ["a"]
    assert redis.calls == ["SCAN 1000", "SCAN 1000", "PIPELINE 1 GET"]


@pytest.mark.asyncio
async def test_a_scope_deleted_between_the_scan_and_its_read_is_left_out():
    redis = _Redis()
    repository = _stored(redis, ["a", "b", "c"])
    redis.values[b"permit.io/Scope:b"] = None  # GET answers nil for a deleted key

    scopes = await repository.all()

    assert [s.scope_id for s in scopes] == ["a", "c"]


@pytest.mark.asyncio
async def test_a_record_that_does_not_parse_still_raises():
    redis = _Redis()
    repository = _stored(redis, ["a"])
    redis.values[b"permit.io/Scope:a"] = b"{not a scope"

    with pytest.raises(ValidationError):
        await repository.all()


@pytest.mark.asyncio
async def test_parsing_the_records_never_stalls_the_event_loop(monkeypatch):
    """Mutation: parsing on the loop (no run_sync) lags the loop by every
    record's parse and fails here."""
    redis = _Redis()
    repository = _stored(redis, [f"s{i:02d}" for i in range(30)])
    parse = Scope.model_validate_json

    def _slow_parse(*args, **kwargs):
        time.sleep(PARSE_SECONDS)
        return parse(*args, **kwargs)

    monkeypatch.setattr(Scope, "model_validate_json", _slow_parse)
    loop = asyncio.get_running_loop()
    lags = []
    done = asyncio.Event()

    async def _tick():
        while not done.is_set():
            started = loop.time()
            await asyncio.sleep(0.005)
            lags.append(loop.time() - started - 0.005)

    ticker = asyncio.create_task(_tick())
    await asyncio.sleep(0.02)
    try:
        scopes = await repository.all()
    finally:
        done.set()
        await ticker

    assert len(scopes) == 30
    assert max(lags) < MAX_LAG_SECONDS, f"the loop stalled {max(lags):.2f}s"
