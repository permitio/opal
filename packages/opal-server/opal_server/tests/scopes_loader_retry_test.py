"""The leader stores the default scope (OPAL_POLICY_REPO_URL) in Redis within a
time limit per try, and tries again until Redis answers: a Redis that is down
or hangs when a worker becomes leader delays its first sync, and never ends or
wedges its leadership."""

import asyncio

import pytest
from opal_server.config import opal_server_config
from opal_server.scopes import loader as loader_module
from opal_server.scopes.loader import DEFAULT_SCOPE_ID, load_scopes
from redis.exceptions import ConnectionError as RedisConnectionError

_URL = "https://git.example.com/org/policy.git"


class _Store:
    """A scope store whose put fails, hangs, or stores, as told."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.stored = []
        self.attempts = 0
        self.release = asyncio.Event()

    async def put(self, scope):
        self.attempts += 1
        outcome = self._outcomes.pop(0) if self._outcomes else "ok"
        if outcome == "refuse":
            raise RedisConnectionError("Error 111 connecting to localhost:6379.")
        if outcome == "hang":
            await self.release.wait()
        if outcome == "broken":
            raise ValueError("not a Redis failure")
        self.stored.append(scope)


@pytest.fixture
def quick(monkeypatch):
    """A 0.05 s limit per try, and retries from 1 ms doubling to 4 ms."""
    monkeypatch.setattr(loader_module, "_STORE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(loader_module, "_RETRY_MIN_SECONDS", 0.001)
    monkeypatch.setattr(loader_module, "_RETRY_MAX_SECONDS", 0.004)


@pytest.fixture
def logs(monkeypatch):
    seen = []
    for level in ("error", "info"):
        monkeypatch.setattr(
            loader_module.logger,
            level,
            lambda message, *a, _level=level, **k: seen.append((_level, message, k)),
        )
    return seen


@pytest.fixture
def default_scope(monkeypatch):
    monkeypatch.setattr(opal_server_config, "POLICY_REPO_URL", _URL)


def _errors(logs):
    return [(m, k) for level, m, k in logs if level == "error"]


@pytest.mark.asyncio
async def test_a_refusing_redis_is_retried_until_the_scope_is_stored(
    default_scope, quick, logs
):
    store = _Store(["refuse", "refuse"])
    await load_scopes(store)
    assert store.attempts == 3
    assert [scope.scope_id for scope in store.stored] == [DEFAULT_SCOPE_ID]
    errors = _errors(logs)
    assert [k["attempt"] for _, k in errors] == [1, 2]
    assert all("ConnectionError" in k["err"] for _, k in errors)
    assert any(level == "info" and "after" in m for level, m, _ in logs), logs


@pytest.mark.parametrize(
    "outcomes, said", [([], []), (["refuse"], [2])], ids=["first-try", "second-try"]
)
@pytest.mark.asyncio
async def test_a_store_after_a_retry_says_how_many_tries_it_took(
    default_scope, quick, logs, outcomes, said
):
    await load_scopes(_Store(outcomes))

    assert [
        k["attempt"] for level, m, k in logs if level == "info" and "tries" in m
    ] == said


@pytest.mark.asyncio
async def test_a_hanging_redis_is_given_up_on_after_the_limit_and_retried(
    default_scope, quick, logs
):
    store = _Store(["hang", "hang"])
    await asyncio.wait_for(load_scopes(store), timeout=5)
    assert store.attempts == 3
    assert len(store.stored) == 1
    assert all("TimeoutError" in k["err"] for _, k in _errors(logs))


@pytest.mark.asyncio
async def test_the_retry_doubles_to_its_cap_with_jitter(default_scope, quick, logs):
    store = _Store(["refuse"] * 6)
    await load_scopes(store)
    delays = [k["delay"] for _, k in _errors(logs)]
    bases = [0.001, 0.002, 0.004, 0.004, 0.004, 0.004]
    assert len(delays) == len(bases)
    for delay, base in zip(delays, bases):
        assert base / 2 <= delay <= base


def test_the_store_is_bounded_and_backed_off_as_the_redis_broadcaster_is():
    from opal_server import broadcast_redis

    assert (
        loader_module._STORE_TIMEOUT_SECONDS == broadcast_redis.PUBLISH_TIMEOUT_SECONDS
    )
    assert loader_module._RETRY_MIN_SECONDS == 0.5
    assert loader_module._RETRY_MAX_SECONDS == 30.0


@pytest.mark.asyncio
async def test_an_error_that_is_not_redis_s_is_raised_at_once(
    default_scope, quick, logs
):
    store = _Store(["broken"])
    with pytest.raises(ValueError):
        await load_scopes(store)
    assert store.attempts == 1
    assert _errors(logs) == []


@pytest.mark.asyncio
async def test_no_default_scope_touches_no_redis(monkeypatch, quick):
    monkeypatch.setattr(opal_server_config, "POLICY_REPO_URL", None)
    store = _Store(["hang"])
    await asyncio.wait_for(load_scopes(store), timeout=1)
    assert store.attempts == 0


@pytest.mark.asyncio
async def test_a_cancelled_load_stops_retrying(default_scope, monkeypatch):
    monkeypatch.setattr(loader_module, "_STORE_TIMEOUT_SECONDS", 10.0)
    store = _Store(["hang"])
    loading = asyncio.create_task(load_scopes(store))
    await asyncio.sleep(0.01)
    loading.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loading
    assert store.attempts == 1
