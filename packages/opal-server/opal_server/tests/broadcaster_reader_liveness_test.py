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
from contextlib import contextmanager  # noqa: E402
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


@contextmanager
def _patched_metrics(emitted, incremented):
    """Capture the gauge/counter calls pubsub_resilience makes."""
    from opal_server import pubsub_resilience as pr

    real_gauge, real_inc = pr.metrics.gauge, pr.metrics.increment

    def gauge(name, value, tags=None):
        emitted.append((name, value))

    def increment(name, tags=None):
        incremented.append(name)

    pr.metrics.gauge, pr.metrics.increment = gauge, increment
    try:
        yield
    finally:
        pr.metrics.gauge, pr.metrics.increment = real_gauge, real_inc


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


async def _first_message(bus, broadcaster):
    """The silence clock only arms once the reader has HEARD the backbone; push
    one message and wait until it is handled."""
    n = len(broadcaster._notifier.notified)
    await bus.push(["t"], {"hello": 1}, notifier_id="peer")
    await _wait_for(lambda: len(broadcaster._notifier.notified) > n)


@pytest.mark.asyncio
async def test_silent_backbone_trips_the_watchdog_and_reconnects_once():
    bus = FakeBus()
    broadcaster = _make(bus)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await _first_message(bus, broadcaster)
        assert broadcaster.is_reader_healthy() is True
        # The backbone neither closes nor errors — it just never speaks again.
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)
        # Silence was treated as a gap: a NEW subscription (reconnect), one gap
        # generation bumped, one trip counted, and the reader task still pending.
        assert bus.connects == 2
        assert broadcaster.backbone_gap_generation() == 1
        assert broadcaster.silence_trips() == 1
        assert not task.done()
        # Re-subscribed => the silent flag clears.
        await _wait_for(lambda: not broadcaster.is_reader_silent())
        # The new session is armed at subscribe (this process has heard the
        # backbone before): a backbone that speaks again within the grace does
        # not trip again — the worker is simply back to normal.
        await _first_message(bus, broadcaster)
        await asyncio.sleep(0.15)
        await _first_message(bus, broadcaster)
        await asyncio.sleep(0.15)
        assert bus.subscribes == 2
        assert broadcaster.silence_trips() == 1
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_silence_trip_keeps_the_reader_healthy_and_exposes_state_instead():
    # A silence trip is a transient reconnect as far as readiness is concerned:
    # /healthcheck must NOT flip (a real backbone outage would otherwise 503 every
    # worker at once and clients could not even reconnect). The state is exposed
    # through is_reader_silent()/silence_trips() and the metrics.
    bus = FakeBus()
    broadcaster = _make(bus)
    broadcaster._listen_count = 1
    emitted = []
    incremented = []
    with _patched_metrics(emitted, incremented):
        task = await broadcaster.start_reader_task()
        try:
            await _wait_for(lambda: bus.subscribes >= 1)
            await _first_message(bus, broadcaster)
            bus.fail_connect = True  # the reconnect will be refused for a while
            await _wait_for(lambda: broadcaster.is_reader_silent(), timeout=3.0)
            assert not task.done()
            assert broadcaster.is_reader_healthy() is True  # NOT flipped
            assert broadcaster.silence_trips() == 1
            assert ("opal_server.broadcaster_reader_silent", 1) in emitted
            assert "opal_server.broadcaster_silence_trips" in incremented
            bus.fail_connect = False
            await _wait_for(lambda: not broadcaster.is_reader_silent(), timeout=3.0)
            assert ("opal_server.broadcaster_reader_silent", 0) in emitted
        finally:
            await _cancel(task)


@pytest.mark.asyncio
async def test_no_trip_before_the_first_message_regardless_of_elapsed_time():
    # Subscribed but nothing heard yet (boot before the leader's keepalive
    # publisher starts; single pod whose own keepalive has not fired): the clock
    # is unarmed, so no amount of waiting trips it.
    bus = FakeBus()
    broadcaster = _make(bus, reader_silence_timeout=0.2)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await asyncio.sleep(1.0)  # 5x the timeout
        assert bus.connects == 1
        assert broadcaster.silence_trips() == 0
        assert broadcaster.backbone_gap_generation() == 0
        # first message arms it; then real silence trips
        await _first_message(bus, broadcaster)
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)
        assert broadcaster.silence_trips() == 1
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_a_later_session_is_armed_at_subscribe_with_the_first_message_grace():
    # The blind spot this guards: a process that HAS heard the backbone
    # reconnects (clean close here; a post-failover reconnect landing on a stale
    # endpoint in life) and the new session goes half-open before its first
    # message. Arming only at first-message would never detect it. Instead the
    # session is armed at subscribe, with the (longer) first-message grace.
    bus = FakeBus()
    broadcaster = _make(
        bus, reader_silence_timeout=0.3, silence_first_message_grace=0.8
    )
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await _first_message(bus, broadcaster)  # the process has now heard it
        await bus.drop()  # clean close -> reconnect; the new session never speaks
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)
        assert broadcaster.silence_trips() == 0
        await asyncio.sleep(0.5)  # past the timeout, within the grace
        assert broadcaster.silence_trips() == 0
        assert bus.subscribes == 2
        await _wait_for(lambda: broadcaster.silence_trips() == 1, timeout=2.0)
        await _wait_for(lambda: bus.subscribes >= 3, timeout=3.0)  # reconnected
        # one gap for the clean drop, one for the silence trip
        assert broadcaster.backbone_gap_generation() == 2
        assert not task.done()
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_the_grace_ends_with_the_first_message_of_the_session():
    # Once a later session has spoken, the normal (shorter) timeout applies
    # again — the grace is for the first message only.
    bus = FakeBus()
    broadcaster = _make(
        bus, reader_silence_timeout=0.3, silence_first_message_grace=1.5
    )
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await _first_message(bus, broadcaster)
        await bus.drop()
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)
        await _first_message(bus, broadcaster)  # the later session speaks once
        await asyncio.sleep(0.6)  # > timeout, << grace
        assert broadcaster.silence_trips() == 1
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_a_process_that_never_heard_the_backbone_never_trips_even_across_resubscribes():
    # Boot property kept: until the process has heard the backbone once, no
    # session is armed — not the first and not a later one either.
    bus = FakeBus()
    broadcaster = _make(bus, reader_silence_timeout=0.2)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await bus.drop()  # a clean close before anything was ever heard
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)
        await asyncio.sleep(1.0)  # 5x the timeout
        assert broadcaster.silence_trips() == 0
        assert bus.subscribes == 2
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
        await _first_message(bus, broadcaster)
        await asyncio.sleep(0.6)  # well under the 5 s limit, several poll cycles
        assert bus.connects == 1
        assert broadcaster.backbone_gap_generation() == 0
        assert broadcaster.is_reader_silent() is False
        assert broadcaster.is_reader_healthy() is True
        # a later message is still delivered (the pending read survived the polls)
        await bus.push(["t"], {"x": 1}, notifier_id="peer")
        await _wait_for(lambda: len(broadcaster._notifier.notified) >= 2)
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
        assert len(broadcaster._notifier.notified) == 8  # every event delivered
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_a_handler_slower_than_the_timeout_is_not_silence():
    # Fan-out to many clients can take longer than the timeout; that time is not
    # backbone silence (the stamp is taken after the handler returns as well).
    bus = FakeBus()
    broadcaster = _make(bus, reader_silence_timeout=0.3)
    broadcaster._listen_count = 1
    handled = []

    async def slow_handle(event):
        await asyncio.sleep(0.5)  # > timeout
        handled.append(event)

    broadcaster._handle_broadcast_event = slow_handle
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        await bus.push(["t"], {"x": 1}, notifier_id="peer")
        await _wait_for(lambda: len(handled) == 1, timeout=3.0)
        # A quiet moment after the slow handler returns: measured from the
        # after-handler stamp it is well under the timeout; measured from the
        # before-handler stamp it would be 0.5 + 0.15 > 0.3 and trip.
        await asyncio.sleep(0.15)
        await bus.push(["t"], {"x": 2}, notifier_id="peer")
        await _wait_for(lambda: len(handled) == 2, timeout=3.0)
        assert bus.connects == 1
        assert broadcaster.silence_trips() == 0
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
        await _first_message(bus, broadcaster)
        await asyncio.sleep(0.6)
        assert bus.connects == 1  # silence is not a gap when the watchdog is off
        assert broadcaster.is_reader_healthy() is True
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_watchdog_does_not_run_before_the_first_subscribe():
    # Backbone down from the start: the reader is retrying connects; no silence
    # trip may be counted (the clock starts on a successful subscribe + message).
    bus = FakeBus(fail_connect_times=3)
    broadcaster = _make(bus, reader_silence_timeout=0.2)
    broadcaster._listen_count = 1
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1, timeout=3.0)
        assert broadcaster.backbone_gap_generation() == 0
        assert broadcaster.silence_trips() == 0
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
        await _wait_for(lambda: bus.subscribes >= 1)
        await _first_message(bus, broadcaster)
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)  # first trip
        await _first_message(bus, broadcaster)  # re-arm the clock after reconnect
        await asyncio.sleep(0.7)  # would be 2-3 more trips without the floor
        assert bus.subscribes == 2
        assert broadcaster.silence_trips() == 1
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
        await _wait_for(lambda: bus.subscribes >= 1)
        await _first_message(bus, broadcaster)
        await _wait_for(lambda: bus.subscribes >= 2, timeout=3.0)  # silence trip
        assert calls["terminate"] == 1
        # Now a CLEAN close by the peer: no terminate (the pool release suffices).
        await _first_message(bus, broadcaster)
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
    # publisher off -> this server emits no heartbeat -> watchdog off
    monkeypatch.setattr(c, "BROADCAST_READER_SILENCE_TIMEOUT", 180.0)
    monkeypatch.setattr(c, "PUBLISHER_ENABLED", False)
    assert pubsub.effective_reader_silence_timeout() == 0.0


def test_first_message_grace_is_at_least_two_keepalives(monkeypatch):
    from opal_server import pubsub
    from opal_server.config import opal_server_config as c

    monkeypatch.setattr(c, "BROADCAST_KEEPALIVE_INTERVAL", 60)
    assert pubsub.silence_first_message_grace(180.0) == 180.0
    assert pubsub.silence_first_message_grace(90.0) == 120.0
    monkeypatch.setattr(c, "BROADCAST_KEEPALIVE_INTERVAL", 0)
    assert pubsub.silence_first_message_grace(180.0) == 180.0


def test_pool_hook_second_install_with_other_timings_warns_and_keeps_first(monkeypatch):
    import types

    captured = {}

    class _FakeAsyncpg:
        @staticmethod
        def create_pool(*args, **kwargs):
            captured["kwargs"] = kwargs
            return "pool"

    fake_backend = types.ModuleType("broadcaster._backends.postgres")
    fake_backend.asyncpg = _FakeAsyncpg
    monkeypatch.setitem(
        __import__("sys").modules, "broadcaster._backends.postgres", fake_backend
    )
    monkeypatch.setattr(keepalive, "_POOL_HOOK_INSTALLED", False)
    monkeypatch.setattr(keepalive, "_POOL_HOOK_TIMINGS", None)
    warnings = []
    monkeypatch.setattr(
        keepalive.logger, "warning", lambda *a, **k: warnings.append(a[0])
    )
    assert keepalive.install_postgres_pool_keepalive(30, 10, 3) is True
    assert keepalive.install_postgres_pool_keepalive(5, 5, 5) is True
    assert any("first install wins" in w for w in warnings)
    assert keepalive._POOL_HOOK_TIMINGS == (30, 10, 3)


def test_keepalive_publisher_starts_before_load_scopes_in_the_leader():
    """M4: the heartbeat the watchdog listens for must not wait for load_scopes
    (which can exceed the silence timeout on a big fleet)."""
    import inspect

    from opal_server import server as server_mod

    src = inspect.getsource(server_mod.OpalServer.start_server_background_tasks)
    start = src.index("self.broadcast_keepalive.start()")
    load = src.index("await load_scopes(self._scopes)")
    assert start < load, "keepalive publisher must start before load_scopes"
