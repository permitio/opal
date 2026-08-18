"""P5 (PR3 fixes): every worker must READ the backbone when scopes are on.

The fleet purge (scopes/purge.py) is delivered over the broadcast channel, but a
worker's EventBroadcaster reader is only started while that worker has a
WebSocket client (or by the statistics path, which is off in every Permit env).
So the confirmed purge never reached client-less workers and they kept stale
GitPolicyFetcher caches for the life of the process (staging, 2026-08-18: 5 of
8 workers per pod never purged once). These tests pin the wiring:

  * SCOPES on, STATISTICS off, broadcaster configured -> the worker enters the
    global listening context exactly once (before it blocks on leadership);
  * SCOPES on AND STATISTICS on -> still exactly once (no double-enter);
  * no broadcaster (single process) -> no context at all.
"""
import asyncio

import pytest
from opal_common.config import opal_common_config
from opal_server import server as server_module
from opal_server.config import opal_server_config
from opal_server.server import OpalServer


class _FakeReaderTask:
    def add_done_callback(self, cb):
        self.cb = cb


class _FakeEventBroadcaster:
    def get_reader_task(self):
        return _FakeReaderTask()


class _FakeListeningContext:
    """Stands in for EventBroadcasterContextManager: counts enters/exits."""

    def __init__(self):
        self.entered = 0
        self.exited = 0
        self.entered_event = asyncio.Event()
        self._event_broadcaster = _FakeEventBroadcaster()

    async def __aenter__(self):
        self.entered += 1
        self.entered_event.set()
        return self

    async def __aexit__(self, *exc):
        self.exited += 1


class _FakePublisher:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _BlockingLock:
    """A leadership lock that never grants: the worker under test is a NON-leader
    (the case that matters — leaders always listen for their own reasons)."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        await asyncio.Event().wait()  # block until cancelled

    async def __aexit__(self, *exc):
        return False


class _FakeStatistics:
    async def run(self):
        await asyncio.Event().wait()

    def remove_client(self, *a, **k):
        pass


@pytest.fixture
def scopes_config(monkeypatch, tmp_path):
    saved = {
        "SCOPES": opal_server_config.SCOPES,
        "REDIS_URL": opal_server_config.REDIS_URL,
        "LEADER_LOCK_FILE_PATH": opal_server_config.LEADER_LOCK_FILE_PATH,
    }
    opal_server_config.SCOPES = True
    opal_server_config.REDIS_URL = "redis://localhost:6379"  # never connected
    opal_server_config.LEADER_LOCK_FILE_PATH = str(tmp_path / "leader.lock")
    yield
    for key, value in saved.items():
        setattr(opal_server_config, key, value)


@pytest.fixture
def statistics(monkeypatch):
    def _set(enabled: bool):
        monkeypatch.setattr(opal_common_config, "STATISTICS_ENABLED", enabled)

    return _set


def _build(broadcaster_uri):
    return OpalServer(
        init_policy_watcher=False,
        init_publisher=False,  # replaced by a fake below; a real one would publish
        broadcaster_uri=broadcaster_uri,
        enable_jwks_endpoint=False,
    )


async def _run_until_entered(server, ctx, monkeypatch, timeout=5.0):
    """Drive start_server_background_tasks on a non-leader worker until the
    listening context is entered (or the timeout), then cancel it."""
    monkeypatch.setattr(server_module, "NamedLock", _BlockingLock)
    monkeypatch.setattr(server_module, "load_scopes", _never_called)
    subscribed = []

    async def _fake_subscribe(endpoint):
        subscribed.append(endpoint)

    monkeypatch.setattr(
        server_module, "subscribe_worker_purge_handler", _fake_subscribe
    )
    server.publisher = _FakePublisher()
    server.broadcast_keepalive = None
    task = asyncio.create_task(server.start_server_background_tasks())
    try:
        await asyncio.wait_for(ctx.entered_event.wait(), timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    return subscribed


async def _never_called(*a, **k):
    raise AssertionError("load_scopes is leader-only and this worker is not the leader")


@pytest.mark.asyncio
async def test_scopes_worker_enters_the_listening_context_without_statistics(
    scopes_config, statistics, monkeypatch
):
    statistics(False)
    server = _build("postgres://localhost/test")
    assert (
        server.broadcast_listening_context is not None
    ), "with SCOPES on and a broadcaster, every worker must hold the global listening context"
    ctx = _FakeListeningContext()
    server.broadcast_listening_context = ctx

    subscribed = await _run_until_entered(server, ctx, monkeypatch)

    assert (
        ctx.entered == 1
    ), "client-less worker never started reading the backbone: fleet purges would not reach it"
    assert subscribed, "purge handler subscription must still be registered"


@pytest.mark.asyncio
async def test_scopes_and_statistics_enter_the_context_exactly_once(
    scopes_config, statistics, monkeypatch
):
    statistics(True)
    server = _build("postgres://localhost/test")
    assert server.broadcast_listening_context is not None
    ctx = _FakeListeningContext()
    server.broadcast_listening_context = ctx
    server.opal_statistics = _FakeStatistics()

    await _run_until_entered(server, ctx, monkeypatch)

    assert (
        ctx.entered == 1
    ), "the context must be entered once even when both statistics and scopes want it"


def test_no_broadcaster_means_no_listening_context(scopes_config, statistics):
    statistics(False)
    server = _build(None)
    assert (
        server.broadcast_listening_context is None
    ), "single-process deployment: nothing to read from"
