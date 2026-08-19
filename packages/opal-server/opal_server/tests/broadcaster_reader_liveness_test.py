"""Reader liveness: a half-open backbone connection must not leave a worker
deaf forever.

Background (observed live): after a Multi-AZ failover of the broadcaster
database the reader's LISTEN connection to the OLD primary stayed
TCP-ESTABLISHED but never delivered anything again; the reader task waited
forever, ``is_reader_healthy()`` stayed True, and the worker's clients silently
missed every update published elsewhere. These tests model that with a
backbone that simply goes quiet (no close, no error) and check that:

* the silence watchdog trips after ``reader_silence_timeout`` and the EXISTING
  reconnect + gap-recovery path runs, exactly once per trip;
* it does NOT trip during ordinary short silences, before the first
  subscribe, or when the watchdog is disabled;
* ``is_reader_healthy()`` goes False while tripped and back to True on
  re-subscribe;
* the dead listening connection is terminated (not handed back to the pool);
* TCP keepalive is applied on connect, skipped gracefully where unsupported,
  and the pool hook wraps ``create_pool`` with an ``init``;
* the config defaults and the keepalive/timeout coupling guard behave.
"""
import asyncio
import socket
import time
from types import SimpleNamespace

import pytest
from opal_server import broadcaster_keepalive as keepalive
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.tests.reconnecting_broadcaster_test import (
    FakeBus,
    FakeNotifier,
    _wait_for,
)

# --------------------------------------------------------------------- helpers


def _make(bus, **overrides):
    kwargs = dict(
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
        reader_silence_timeout=0.3,
        silence_min_trip_interval=0,
        silence_poll_seconds=0.05,
    )
    kwargs.update(overrides)
    return ReconnectingBroadcaster("memory://", **kwargs)


async def _cancel(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ------------------------------------------------------------ silence watchdog


@pytest.mark.asyncio
async def test_silent_backbone_trips_the_watchdog_and_reconnects_once():
    bus = FakeBus()
    broadcaster = _make(bus)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        assert broadcaster.is_reader_healthy() is True
        # The backbone neither closes nor errors — it just never speaks again.
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)
        # Silence was treated as a gap: a NEW subscription (reconnect), one gap
        # generation bumped, and the reader task still pending.
        assert bus.connects == 2
        assert broadcaster.backbone_gap_generation() == 1
        assert not task.done()
        # Re-subscribed => healthy again and the silent flag cleared.
        await _wait_for(lambda: broadcaster.is_reader_healthy())
        assert broadcaster.is_reader_silent() is False
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_watchdog_marks_reader_unhealthy_while_tripped_and_not_resubscribed():
    # After the trip the reconnect must FAIL for a while (connect refused), so we
    # can observe the unhealthy window: pending task, listeners present, but the
    # watchdog said "deaf" and nothing has re-subscribed yet.
    bus = FakeBus()
    broadcaster = _make(bus)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        bus.fail_connect = True  # reconnect attempts will be refused
        await _wait_for(lambda: broadcaster.is_reader_silent(), timeout=3.0)
        assert not task.done()
        assert broadcaster.is_reader_healthy() is False
        # Backbone comes back: the next connect succeeds, health recovers.
        bus.fail_connect = False
        await _wait_for(lambda: broadcaster.is_reader_healthy(), timeout=3.0)
        assert broadcaster.is_reader_silent() is False
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_short_silence_does_not_trip():
    bus = FakeBus()
    broadcaster = _make(bus, reader_silence_timeout=5.0)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await asyncio.sleep(0.6)  # well under the 5 s limit, several poll cycles
        assert bus.connects == 1
        assert broadcaster.backbone_gap_generation() == 0
        assert broadcaster.is_reader_silent() is False
        assert broadcaster.is_reader_healthy() is True
        # a message resets the clock (and is still delivered)
        await bus.push(["t"], {"x": 1}, notifier_id="peer")
        await _wait_for(lambda: broadcaster._notifier.notified)
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_messages_keep_the_watchdog_quiet():
    # Steady traffic spaced well under the limit must never trip, however long it lasts.
    bus = FakeBus()
    broadcaster = _make(bus, reader_silence_timeout=0.3)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        for _ in range(8):
            await bus.push(["t"], {"x": 1}, notifier_id="peer")
            await asyncio.sleep(0.1)
        assert bus.connects == 1
        assert broadcaster.backbone_gap_generation() == 0
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_watchdog_disabled_means_plain_passthrough():
    bus = FakeBus()
    broadcaster = _make(bus, reader_silence_timeout=0)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await asyncio.sleep(0.6)
        assert bus.connects == 1  # silence is not a gap when the watchdog is off
        assert broadcaster.is_reader_healthy() is True
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_watchdog_does_not_run_before_the_first_subscribe():
    # Backbone down from the start: the reader is retrying connects; no silence
    # trip may be counted (the clock starts on a successful subscribe).
    bus = FakeBus(fail_connect_times=3)
    broadcaster = _make(bus, reader_silence_timeout=0.2)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1, timeout=3.0)
        assert broadcaster.backbone_gap_generation() == 0
        assert broadcaster._last_silence_trip_at is None
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_trip_floor_limits_reconnect_storm():
    # silence_min_trip_interval=10 s: after one trip, a second silence within
    # the floor does NOT trip again (the gap recovery runs once).
    bus = FakeBus()
    broadcaster = _make(bus, reader_silence_timeout=0.2, silence_min_trip_interval=10)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)  # first trip
        await asyncio.sleep(0.6)  # would be 2-3 more trips without the floor
        assert bus.subscribes == 2
        assert broadcaster.backbone_gap_generation() == 1
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_silence_trip_terminates_the_listening_connection_before_release():
    # The dead socket must be killed (asyncpg terminate) before the channel is
    # released back to the pool — otherwise the reconnect reuses the half-open
    # connection. Modelled with a channel exposing a backend whose _conn has
    # terminate(); on a peer-announced close terminate() must NOT be called.
    bus = FakeBus()
    calls = {"terminate": 0}

    class _Conn:
        def terminate(self):
            calls["terminate"] += 1

    real_factory = bus.channel_factory

    def factory(url):
        channel = real_factory(url)
        channel._backend = SimpleNamespace(_conn=_Conn())
        return channel

    broadcaster = _make(bus, broadcast_type=factory, reader_silence_timeout=0.2)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)  # silence trip
        assert calls["terminate"] == 1
        # Now a CLEAN close by the peer: no terminate (the pool release suffices).
        await bus.push(["t"], {"x": 1}, notifier_id="peer")  # proves liveness first
        await bus.drop()
        await _wait_for(lambda: bus.subscribes >= 3, timeout=3.0)
        assert calls["terminate"] == 1
    finally:
        await _cancel(task)


# ---------------------------------------------------------------- keepalive


class _FakeSocket:
    def __init__(self, refuse_timings=False, refuse_all=False):
        self.opts = []
        self.refuse_timings = refuse_timings
        self.refuse_all = refuse_all

    def setsockopt(self, level, opt, value):
        if self.refuse_all:
            raise OSError("nope")
        if self.refuse_timings and level == socket.IPPROTO_TCP:
            raise OSError("unsupported option")
        self.opts.append((level, opt, value))


def test_apply_tcp_keepalive_sets_flag_and_timings():
    sock = _FakeSocket()
    assert keepalive.apply_tcp_keepalive(sock, 30, 10, 3) is True
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in sock.opts
    idle_opt = getattr(socket, "TCP_KEEPIDLE", None) or getattr(
        socket, "TCP_KEEPALIVE", None
    )
    tcp_opts = {opt: val for lvl, opt, val in sock.opts if lvl == socket.IPPROTO_TCP}
    if idle_opt is not None:
        assert tcp_opts[idle_opt] == 30
    if getattr(socket, "TCP_KEEPINTVL", None) is not None:
        assert tcp_opts[socket.TCP_KEEPINTVL] == 10
    if getattr(socket, "TCP_KEEPCNT", None) is not None:
        assert tcp_opts[socket.TCP_KEEPCNT] == 3


def test_apply_tcp_keepalive_is_fail_open():
    # timings refused -> flag still on, returns True; everything refused -> False;
    # no socket -> False. None of them raise.
    sock = _FakeSocket(refuse_timings=True)
    assert keepalive.apply_tcp_keepalive(sock, 30, 10, 3) is True
    assert sock.opts == [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    assert (
        keepalive.apply_tcp_keepalive(_FakeSocket(refuse_all=True), 30, 10, 3) is False
    )
    assert keepalive.apply_tcp_keepalive(None, 30, 10, 3) is False


def test_apply_keepalive_to_connection_digs_through_pool_proxy_and_transport():
    sock = _FakeSocket()
    transport = SimpleNamespace(
        get_extra_info=lambda name: sock if name == "socket" else None
    )
    inner = SimpleNamespace(_transport=transport)
    proxy = SimpleNamespace(_con=inner)  # asyncpg PoolConnectionProxy shape
    assert keepalive.apply_keepalive_to_connection(proxy, 30, 10, 3) is True
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in sock.opts
    # a connection without a transport is a clean False, not an exception
    assert (
        keepalive.apply_keepalive_to_connection(SimpleNamespace(), 30, 10, 3) is False
    )


@pytest.mark.asyncio
async def test_reconnecting_broadcaster_applies_keepalive_to_its_listener():
    bus = FakeBus()
    sock = _FakeSocket()
    transport = SimpleNamespace(
        get_extra_info=lambda name: sock if name == "socket" else None
    )
    real_factory = bus.channel_factory

    def factory(url):
        channel = real_factory(url)
        channel._backend = SimpleNamespace(_conn=SimpleNamespace(_transport=transport))
        return channel

    broadcaster = _make(
        bus,
        broadcast_type=factory,
        reader_silence_timeout=0,
        tcp_keepalive={"idle": 7, "interval": 2, "count": 4},
    )
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in sock.opts
        idle_opt = getattr(socket, "TCP_KEEPIDLE", None) or getattr(
            socket, "TCP_KEEPALIVE", None
        )
        if idle_opt is not None:
            assert (socket.IPPROTO_TCP, idle_opt, 7) in sock.opts
    finally:
        await _cancel(task)


def test_pool_hook_wraps_create_pool_with_an_init(monkeypatch):
    # Install the hook against a fake backend module and check create_pool gets an
    # init that applies keepalive to the connection it is handed.
    import types

    captured = {}

    class _FakeAsyncpg:
        @staticmethod
        def create_pool(*args, **kwargs):
            captured["kwargs"] = kwargs
            return "pool"

        some_other_attr = "forwarded"

    fake_backend = types.ModuleType("broadcaster._backends.postgres")
    fake_backend.asyncpg = _FakeAsyncpg
    monkeypatch.setitem(
        __import__("sys").modules, "broadcaster._backends.postgres", fake_backend
    )
    monkeypatch.setattr(keepalive, "_POOL_HOOK_INSTALLED", False)

    assert keepalive.install_postgres_pool_keepalive(30, 10, 3) is True
    # idempotent
    assert keepalive.install_postgres_pool_keepalive(30, 10, 3) is True
    assert fake_backend.asyncpg.create_pool("postgres://x", max_size=10) == "pool"
    assert "init" in captured["kwargs"]
    assert fake_backend.asyncpg.some_other_attr == "forwarded"  # other names forwarded

    sock = _FakeSocket()
    transport = SimpleNamespace(
        get_extra_info=lambda name: sock if name == "socket" else None
    )
    conn = SimpleNamespace(_transport=transport)
    asyncio.run(captured["kwargs"]["init"](conn))
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in sock.opts


# ------------------------------------------------------------------ config


def test_config_defaults():
    from opal_server.config import opal_server_config as c

    assert c.BROADCAST_KEEPALIVE_INTERVAL == 60
    assert c.BROADCAST_READER_SILENCE_TIMEOUT == 180.0
    assert c.BROADCAST_TCP_KEEPALIVE_ENABLED is True
    assert c.BROADCAST_TCP_KEEPALIVE_IDLE == 30
    assert c.BROADCAST_TCP_KEEPALIVE_INTERVAL == 10
    assert c.BROADCAST_TCP_KEEPALIVE_COUNT == 3


def test_effective_silence_timeout_is_coupled_to_the_keepalive(monkeypatch):
    from opal_server import pubsub
    from opal_server.config import opal_server_config as c

    monkeypatch.setattr(c, "BROADCAST_KEEPALIVE_INTERVAL", 60)
    monkeypatch.setattr(c, "BROADCAST_READER_SILENCE_TIMEOUT", 180.0)
    assert pubsub.effective_reader_silence_timeout() == 180.0
    # below 2x keepalive -> raised to 2x (one late keepalive cannot trip it)
    monkeypatch.setattr(c, "BROADCAST_READER_SILENCE_TIMEOUT", 70.0)
    assert pubsub.effective_reader_silence_timeout() == 120.0
    # no keepalive -> watchdog off (a quiet channel would look dead)
    monkeypatch.setattr(c, "BROADCAST_KEEPALIVE_INTERVAL", 0)
    monkeypatch.setattr(c, "BROADCAST_READER_SILENCE_TIMEOUT", 180.0)
    assert pubsub.effective_reader_silence_timeout() == 0.0
    # explicitly disabled stays disabled
    monkeypatch.setattr(c, "BROADCAST_KEEPALIVE_INTERVAL", 60)
    monkeypatch.setattr(c, "BROADCAST_READER_SILENCE_TIMEOUT", 0)
    assert pubsub.effective_reader_silence_timeout() == 0.0
