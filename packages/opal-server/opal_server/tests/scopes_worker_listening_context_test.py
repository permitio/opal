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
    """Stands in for EventBroadcasterContextManager: counts enters/exits AND
    mirrors the library's shared ``_listen_count`` — incremented in __aenter__
    BEFORE the reader is started, decremented in __aexit__ — because that
    ordering is what the failed-enter unwind is about."""

    def __init__(self):
        self.entered = 0
        self.exited = 0
        self.listen_count = 0
        self.entered_event = asyncio.Event()
        self._event_broadcaster = _FakeEventBroadcaster()

    async def __aenter__(self):
        self.listen_count += 1  # library: count first...
        self.entered += 1
        self.entered_event.set()
        await self._start_reader()  # ...then start the reader (may raise)
        return self

    async def _start_reader(self):
        pass

    async def __aexit__(self, exc_type, exc, tb):  # STRICT arity, like the real one
        self.listen_count -= 1
        self.exited += 1


class _RaisingListeningContext(_FakeListeningContext):
    """The eager-connect failure of the legacy broadcaster: the reader start
    inside __aenter__ raises — AFTER the shared count was incremented."""

    async def _start_reader(self):
        raise ConnectionRefusedError("backbone down at boot")


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


class _GrantingLock:
    """A leadership lock that grants immediately: the worker under test becomes
    the leader, runs the (stubbed) leader block and reaches the exit path."""

    acquired = 0

    def __init__(self, *a, **k):
        _GrantingLock.acquired += 1

    async def __aenter__(self):
        return self

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


async def _run_to_completion(server, monkeypatch, timeout=5.0):
    """Drive start_server_background_tasks on a worker that WINS leadership,
    with no keepalive and no watcher, so the whole background task returns and
    the exit path (listening-context __aexit__) actually executes."""
    _GrantingLock.acquired = 0
    monkeypatch.setattr(server_module, "NamedLock", _GrantingLock)

    async def _fake_load(scopes):
        pass

    monkeypatch.setattr(server_module, "load_scopes", _fake_load)
    subscribed = []

    async def _fake_subscribe(endpoint):
        subscribed.append(endpoint)

    monkeypatch.setattr(
        server_module, "subscribe_worker_purge_handler", _fake_subscribe
    )
    server.publisher = _FakePublisher()
    server.broadcast_keepalive = None
    server._init_policy_watcher = False
    await asyncio.wait_for(server.start_server_background_tasks(), timeout)
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


@pytest.mark.asyncio
async def test_exit_path_leaves_the_listening_context_with_the_right_arity(
    scopes_config, statistics, monkeypatch
):
    """The real EventBroadcasterContextManager.__aexit__(exc_type, exc, tb) has
    no defaults: a zero-arg call raises TypeError inside the un-awaited
    background task, leaving _listen_count at 1 and the reader never
    cancelled — on every scopes LEADER whose watcher stops. The double is
    strict about arity so this cannot regress silently."""
    statistics(False)
    server = _build("postgres://localhost/test")
    ctx = _FakeListeningContext()
    server.broadcast_listening_context = ctx

    await _run_to_completion(server, monkeypatch)

    assert ctx.entered == 1 and ctx.exited == 1, (ctx.entered, ctx.exited)


def test_legacy_broadcaster_does_not_get_a_scopes_reader(
    scopes_config, statistics, monkeypatch
):
    """BROADCAST_RECONNECT_ENABLED=false builds the legacy EventBroadcaster,
    whose reader connects EAGERLY in __aenter__ and re-raises: with the
    backbone down at boot that would abort the background task before the
    purge subscription and the leadership lock. The scopes reason therefore
    applies only to the ReconnectingBroadcaster."""
    statistics(False)
    monkeypatch.setattr(opal_server_config, "BROADCAST_RECONNECT_ENABLED", False)
    infos = []
    monkeypatch.setattr(
        server_module.logger, "info", lambda msg, *a, **k: infos.append(str(msg))
    )
    server = _build("postgres://localhost/test")
    assert not isinstance(
        server.pubsub.broadcaster, server_module.ReconnectingBroadcaster
    )
    assert server.broadcast_listening_context is None
    assert any("BROADCAST_RECONNECT_ENABLED is off" in m for m in infos), infos


@pytest.mark.asyncio
async def test_a_raising_enter_is_logged_and_the_rest_of_the_background_task_still_runs(
    scopes_config, statistics, monkeypatch
):
    """Belt and braces: if entering the context raises anyway, the worker must
    still subscribe the purge handler and take the leadership lock; the failure
    is one WARNING and the context is dropped (so exit does not touch it)."""
    statistics(False)
    server = _build("postgres://localhost/test")
    ctx = _RaisingListeningContext()
    server.broadcast_listening_context = ctx
    warnings = []
    monkeypatch.setattr(
        server_module.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg))
    )

    subscribed = await _run_to_completion(server, monkeypatch)

    assert ctx.entered == 1
    assert subscribed, "purge subscription must still happen after a failed enter"
    assert (
        _GrantingLock.acquired == 1
    ), "leadership must still be attempted after a failed enter"
    assert server.broadcast_listening_context is None
    assert any(
        "Could not start listening on the broadcast channel" in m for m in warnings
    ), warnings
    # The real __aenter__ increments the shared listen count BEFORE it starts the
    # reader, so a raise leaves it at 1 unless we unwind: every later client
    # context would take it to 2, 3, ... and the reader would never start again.
    assert ctx.exited == 1, "a failed enter must be unwound with __aexit__"
    assert ctx.listen_count == 0, "listen count must be back to 0 after the unwind"


def test_legacy_broadcaster_with_statistics_arms_the_context_and_stays_quiet(
    scopes_config, statistics, monkeypatch
):
    """Statistics arm the context on ANY broadcaster (pre-existing behaviour),
    and then purges are delivered too — so the "not guaranteed" INFO line must
    not be logged in that combination."""
    statistics(True)
    monkeypatch.setattr(opal_server_config, "BROADCAST_RECONNECT_ENABLED", False)
    infos = []
    monkeypatch.setattr(
        server_module.logger, "info", lambda msg, *a, **k: infos.append(str(msg))
    )
    server = _build("postgres://localhost/test")
    assert server.broadcast_listening_context is not None
    assert not any("BROADCAST_RECONNECT_ENABLED is off" in m for m in infos), infos


class _FakeWatcher:
    """A watcher whose run ends immediately: the mainline leader shape
    (watcher stops -> _graceful_shutdown -> exit path)."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def wait_until_should_stop(self):
        return None


@pytest.mark.asyncio
async def test_exit_path_through_the_mainline_watcher_shape(
    scopes_config, statistics, monkeypatch
):
    """Same invariant as the fall-through test, but through the shape prod
    actually takes: leader runs the watcher, the watcher stops, the worker
    asks for a graceful shutdown and the listening context is exited once."""
    statistics(False)
    server = _build("postgres://localhost/test")
    ctx = _FakeListeningContext()
    server.broadcast_listening_context = ctx
    shutdowns = []
    monkeypatch.setattr(server, "_graceful_shutdown", lambda: shutdowns.append(1))
    monkeypatch.setattr(
        server_module, "setup_watcher_task", lambda *a, **k: _FakeWatcher()
    )
    _GrantingLock.acquired = 0
    monkeypatch.setattr(server_module, "NamedLock", _GrantingLock)

    async def _fake_load(scopes):
        pass

    async def _fake_subscribe(endpoint):
        pass

    monkeypatch.setattr(server_module, "load_scopes", _fake_load)
    monkeypatch.setattr(
        server_module, "subscribe_worker_purge_handler", _fake_subscribe
    )
    server.publisher = _FakePublisher()
    server.broadcast_keepalive = None
    server._init_policy_watcher = True

    await asyncio.wait_for(server.start_server_background_tasks(), 5.0)

    assert shutdowns == [1], "watcher stop must request a graceful shutdown"
    assert ctx.entered == 1 and ctx.exited == 1 and ctx.listen_count == 0
