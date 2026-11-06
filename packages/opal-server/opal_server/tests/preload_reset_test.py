"""preload_scopes() wiring: the gunicorn master must reset the fetcher caches
right after clearing git-executor bookkeeping, so forked workers inherit
neither (fix P).

A non-leader worker never populates GitPolicyFetcher.repos itself (sync,
the only writer, is leader-only) — its only entries would be ones
inherited from the master's preload fork. Since the fleet-wide purge
broadcast only reaches a worker whose broadcaster reader is running, a
client-less non-leader worker could never drop an inherited handle.
Clearing the caches in the master before fork means workers start (and
stay) empty.
"""
import asyncio
import contextlib
import gc
import threading
import time
from typing import List, Optional

import opal_common.logger as opal_common_logger
import opal_server.scopes.task as task_module
import pytest
from opal_server.config import opal_server_config
from opal_server.redis_utils import RedisDB
from opal_server.scopes.scope_repository import ScopeNotFoundError, ScopeRepository
from redis.exceptions import TimeoutError as RedisTimeoutError


@pytest.fixture(autouse=True)
def _logging_already_configured(monkeypatch):
    """scripts/gunicorn_conf.py::when_ready configures logging before it calls
    preload_scopes(), so the preload keeps the sinks already in place. Without
    this, the first preload in a session runs the real configure_logs(), whose
    logger.remove() drops the capture sinks the drain-warning tests add."""
    monkeypatch.setattr(opal_common_logger, "_logs_configured", True)


@pytest.fixture(autouse=True)
def _stub_redis_layer(no_redis, preload_sandbox):
    """Every test here runs preload_scopes(), which evaluates
    ``ScopeRepository(RedisDB(...))`` before the stubbed ScopesService sees
    the arguments: without no_redis each would build a real Redis client.
    preload_sandbox gives the preload no scopes and a BASE_DIR under
    tmp_path, so its hung-clone sweep never touches the BASE_DIR of whoever
    runs the tests.

    The tests about the preload's Redis client replace RedisDB and
    ScopeRepository over these stubs.
    """
    yield


def test_preload_scopes_resets_fetcher_caches_after_shutdown(monkeypatch):
    events = []

    class _StubService:
        def __init__(self, *args, **kwargs):
            pass

        async def sync_scopes(self, *args, **kwargs):
            events.append("sync_scopes")

    def _stub_shutdown_git_executor():
        events.append("shutdown_git_executor")

    class _StubGitPolicyFetcher:
        @staticmethod
        def reset_caches():
            events.append("reset_caches")

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(
        task_module, "shutdown_git_executor", _stub_shutdown_git_executor
    )
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGitPolicyFetcher)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    task_module.ScopesPolicyWatcherTask.preload_scopes()

    assert events == ["sync_scopes", "shutdown_git_executor", "reset_caches"], events


def test_preload_scopes_noop_when_scopes_disabled(monkeypatch):
    """Guards the ordering test's premise: with SCOPES off, nothing in the
    block (including reset_caches) should run at all."""
    events = []

    class _StubGitPolicyFetcher:
        @staticmethod
        def reset_caches():
            events.append("reset_caches")

    monkeypatch.setattr(
        task_module, "shutdown_git_executor", lambda: events.append("shutdown")
    )
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGitPolicyFetcher)
    monkeypatch.setattr(opal_server_config, "SCOPES", False)

    task_module.ScopesPolicyWatcherTask.preload_scopes()

    assert events == []


def test_preload_scopes_drains_before_teardown(monkeypatch):
    events = []

    class _StubService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            events.append("sync_scopes")

    class _StubGPF:
        @staticmethod
        def reset_caches():
            events.append("reset_caches")

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(
        task_module, "drain_git_ops", lambda t: events.append("drain") or True
    )
    monkeypatch.setattr(
        task_module, "shutdown_git_executor", lambda: events.append("shutdown")
    )
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGPF)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    task_module.ScopesPolicyWatcherTask.preload_scopes()
    assert events == ["sync_scopes", "drain", "shutdown", "reset_caches"], events


def test_preload_warns_when_the_drain_times_out_with_ops_still_in_flight(monkeypatch):
    """A drain that times out means git threads survive into the forked
    workers, where they can race a worker on the shared clone dir.

    That is the one condition carrying this risk, and the warning is its
    only signal — nothing else reports it, and reset_caches deliberately
    skips those handles rather than failing loudly. Mutation: drop the
    `if not drained` warning and the whole condition becomes invisible.
    """
    from opal_common.logger import logger as opal_logger

    class _StubService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            return None

    class _StubGPF:
        @staticmethod
        def reset_caches():
            return None

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda t: False)  # timed out
    monkeypatch.setattr(task_module, "git_busy_count", lambda: 3)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGPF)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        opal_logger.remove(sink)

    warned = [r for r in records if "Preload drain timed out" in r]
    assert warned, f"a timed-out drain was not reported at all: {records}"
    # Against the RENDERED payload, not the formatted record: a bare "3" is
    # supplied by the timestamp and the source line number, so `"3" in record`
    # holds for any drain warning at all and cannot fail.
    assert (
        "in flight (3)" in warned[0]
    ), f"the in-flight count is missing from the warning: {warned[0]}"


def test_preload_does_not_warn_when_the_drain_succeeds(monkeypatch):
    """The inverse, so the test above cannot pass by always-warning."""
    from opal_common.logger import logger as opal_logger

    class _StubService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            return None

    class _StubGPF:
        @staticmethod
        def reset_caches():
            return None

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda t: True)  # drained
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(task_module, "GitPolicyFetcher", _StubGPF)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        opal_logger.remove(sink)

    assert not [
        r for r in records if "Preload drain timed out" in r
    ], f"warned on a clean drain: {records}"


async def _read_command(reader: asyncio.StreamReader) -> Optional[List[bytes]]:
    """One RESP command (an array of bulk strings); None at end of file."""
    header = await reader.readline()
    if not header:
        return None
    args = []
    for _ in range(int(header[1:])):
        size = int((await reader.readline())[1:])
        args.append((await reader.readexactly(size + 2))[:-2])
    return args


class _RedisServer:
    """A Redis server on 127.0.0.1, on a thread of its own: it answers every
    GET with nil (no such key), a little late so that reads sent at once are in
    flight at once, and anything else with OK.

    It counts the connections made to it and those still open.
    """

    def __init__(self) -> None:
        self.made = 0
        self.open = 0
        self.port = 0
        self._loop = asyncio.new_event_loop()
        started = threading.Event()
        self._thread = threading.Thread(
            target=self._serve, args=(started,), daemon=True
        )
        self._thread.start()
        assert started.wait(10), "the Redis stand-in never started"

    @property
    def url(self) -> str:
        return f"redis://127.0.0.1:{self.port}/0"

    def _serve(self, started: threading.Event) -> None:
        asyncio.set_event_loop(self._loop)
        server = self._loop.run_until_complete(
            asyncio.start_server(self._client, "127.0.0.1", 0)
        )
        self.port = server.sockets[0].getsockname()[1]
        started.set()
        self._loop.run_forever()
        server.close()

    async def _client(self, reader, writer) -> None:
        self.made += 1
        self.open += 1
        try:
            while (command := await _read_command(reader)) is not None:
                if command[0].upper() == b"GET":
                    await asyncio.sleep(0.05)
                    writer.write(b"$-1\r\n")
                else:
                    writer.write(b"+OK\r\n")
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.open -= 1
            writer.close()

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(10)


def test_preload_closes_its_redis_pool_before_it_returns(monkeypatch):
    """The preload's syncs read their scopes from Redis at once, and the
    client's pool keeps one connection per read in flight at once: hundreds
    with thousands of scopes. All of them are closed by the time
    preload_scopes() returns, so the master holds none and the workers it forks
    inherit none.

    gc stays off meanwhile: the client and its connections are reference
    cycles, which a collection that happened to run would close too, hiding
    a preload that never closed them.

    Mutation: not closing the client leaves every connection open, and so
    does closing it without its pool (a client from_url makes keeps its pool
    open on close() alone in redis-py 4.x).
    """
    server = _RedisServer()
    reads = 5

    class _ReadingService:
        def __init__(self, *, scopes, **kwargs):
            self._scopes = scopes

        async def sync_scopes(self, *args, **kwargs):
            async def _read(i):
                with contextlib.suppress(ScopeNotFoundError):
                    await self._scopes.get(f"s{i}")

            await asyncio.gather(*(_read(i) for i in range(reads)))

    monkeypatch.setattr(task_module, "RedisDB", RedisDB)
    monkeypatch.setattr(task_module, "ScopeRepository", ScopeRepository)
    monkeypatch.setattr(task_module, "ScopesService", _ReadingService)
    monkeypatch.setattr(task_module, "reclone_hung_enabled", lambda: False)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    monkeypatch.setattr(opal_server_config, "REDIS_URL", server.url)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    gc.disable()
    try:
        task_module.ScopesPolicyWatcherTask.preload_scopes()

        assert server.made == reads, "the reads did not overlap; test proves nothing"
        deadline = time.monotonic() + 5
        while server.open and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.open == 0, f"{server.open} of {reads} connections left open"
    finally:
        gc.enable()
        server.stop()


class _CloseFails:
    """A RedisDB whose close() fails, as a connection's disconnect can in
    redis-py 4.x."""

    def __init__(self, url):
        pass

    async def close(self):
        raise RedisTimeoutError("Timed out closing connection after 5")


@pytest.mark.parametrize("sync_fails", [False, True], ids=["sync-ok", "sync-failed"])
def test_a_failed_close_of_the_preloads_redis_client_is_logged_and_left(
    monkeypatch, sync_fails
):
    """scripts/gunicorn_conf.py::when_ready calls preload_scopes() unguarded,
    so an error out of it fails the master's start. A failed close of the
    client the preload is done with is logged at WARNING and left: the preload
    returns, or raises its sync's own error, as it would have with no close.

    Mutation: an unguarded close fails a preload whose sync went fine, and
    replaces the error of one whose sync failed.
    """
    from opal_common.logger import logger as opal_logger

    class _SyncFailed(Exception):
        pass

    class _StubService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            if sync_fails:
                raise _SyncFailed("the sync's own error")

    monkeypatch.setattr(task_module, "RedisDB", _CloseFails)
    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        if sync_fails:
            with pytest.raises(_SyncFailed):
                task_module.ScopesPolicyWatcherTask.preload_scopes()
        else:
            task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        opal_logger.remove(sink)

    warned = [r for r in records if "closing its Redis client failed" in r]
    assert warned, f"the failed close was not logged: {records}"
    assert (
        "Timed out closing connection" in warned[0]
    ), f"the close's error is missing from the warning: {warned[0]}"
