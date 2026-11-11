"""Tests for the Redis broadcaster backend that reports a lost connection.

They run against a small in-process server that speaks enough of the
Redis protocol (AUTH, PING, SUBSCRIBE, UNSUBSCRIBE, PUBLISH) over a real
socket and can be stopped and started again, so a Redis restart is
reproduced without a real Redis.

The scenario under test is permitio/opal#883: after the Redis backbone
restarts, the OPAL server must subscribe to the broadcast channel again
and must know that there was a gap. The last two tests are negative
controls: the stock backend, on the same restart, does neither.
"""
import asyncio
from contextlib import suppress

import pytest
import pytest_asyncio
from broadcaster import Broadcast
from broadcaster._backends.postgres import PostgresBackend
from fastapi_websocket_pubsub import EventBroadcaster
from fastapi_websocket_pubsub.event_broadcaster import BroadcastNotification
from fastapi_websocket_pubsub.util import pydantic_serialize
from opal_server.config import opal_server_config
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.redis_broadcast_backend import (
    ResilientBroadcast,
    ResilientRedisBackend,
    tcp_keepalive_options,
)
from opal_server.server import OpalServer
from redis.exceptions import RedisError

CHANNEL = "EventNotifier"
PASSWORD = "password1234"


def _bulk(value: str) -> bytes:
    data = value.encode()
    return b"$%d\r\n%s\r\n" % (len(data), data)


def _array(*items) -> bytes:
    out = b"*%d\r\n" % len(items)
    for item in items:
        out += b":%d\r\n" % item if isinstance(item, int) else _bulk(item)
    return out


class FakeRedisServer:
    """A restartable, single-process stand-in for a Redis server."""

    def __init__(self, password=None):
        self.password = password
        self.port = None
        self.connections_accepted = 0
        self._server = None
        self._writers = set()
        self._subscribers = {}  # channel -> set of writers

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}127.0.0.1:{self.port}"

    def channels(self) -> set:
        """The channels with at least one subscriber (``PUBSUB CHANNELS``)."""
        return {channel for channel, subs in self._subscribers.items() if subs}

    async def start(self):
        # The first start picks a free port; a restart binds the same one.
        self._server = await asyncio.start_server(
            self._serve, "127.0.0.1", self.port or 0
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        """Stop listening and drop every connection, as a restart does."""
        server, self._server = self._server, None
        if server is None:
            return
        server.close()
        for writer in list(self._writers):
            writer.close()
        with suppress(Exception):
            await asyncio.wait_for(server.wait_closed(), timeout=5)
        self._writers.clear()
        self._subscribers.clear()

    async def restart(self):
        await self.stop()
        await self.start()

    async def _read_command(self, reader):
        header = await reader.readline()
        if not header:
            return None
        args = []
        for _ in range(int(header[1:])):
            length = int((await reader.readline())[1:])
            args.append((await reader.readexactly(length + 2))[:-2].decode())
        return args

    async def _serve(self, reader, writer):
        self.connections_accepted += 1
        self._writers.add(writer)
        authenticated = self.password is None
        subscribed = set()
        try:
            while True:
                args = await self._read_command(reader)
                if not args:
                    break
                command = args[0].upper()
                if command == "AUTH":
                    if args[-1] == self.password:
                        authenticated = True
                        writer.write(b"+OK\r\n")
                    else:
                        writer.write(b"-WRONGPASS invalid username-password pair\r\n")
                elif not authenticated:
                    writer.write(b"-NOAUTH Authentication required.\r\n")
                elif command == "PING":
                    writer.write(b"+PONG\r\n")
                elif command == "SUBSCRIBE":
                    for channel in args[1:]:
                        subscribed.add(channel)
                        self._subscribers.setdefault(channel, set()).add(writer)
                        writer.write(_array("subscribe", channel, len(subscribed)))
                elif command == "UNSUBSCRIBE":
                    for channel in args[1:] or list(subscribed):
                        subscribed.discard(channel)
                        self._subscribers.get(channel, set()).discard(writer)
                        writer.write(_array("unsubscribe", channel, len(subscribed)))
                elif command == "PUBLISH":
                    receivers = list(self._subscribers.get(args[1], ()))
                    for receiver in receivers:
                        receiver.write(_array("message", args[1], args[2]))
                    writer.write(b":%d\r\n" % len(receivers))
                else:
                    writer.write(b"+OK\r\n")
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._writers.discard(writer)
            for channel in subscribed:
                self._subscribers.get(channel, set()).discard(writer)
            writer.close()


class RecordingNotifier:
    """Records what the broadcaster forwards from the backbone."""

    def __init__(self):
        self.notified = []

    async def notify(self, topics, data, notifier_id=None):
        self.notified.append((list(topics), data))


async def _wait_for(condition, timeout=5.0):
    """Wait until ``condition()`` is true; fail the test if it never is."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        assert (
            asyncio.get_running_loop().time() < deadline
        ), "condition was not met in time"
        await asyncio.sleep(0.01)


async def _start_server(password=None) -> FakeRedisServer:
    server = FakeRedisServer(password=password)
    await server.start()
    return server


@pytest_asyncio.fixture
async def redis_server():
    server = await _start_server()
    yield server
    await server.stop()


@pytest_asyncio.fixture
async def redis_server_with_password():
    server = await _start_server(password=PASSWORD)
    yield server
    await server.stop()


def _reconnecting_broadcaster(url, notifier, broadcast_type):
    return ReconnectingBroadcaster(
        url,
        notifier=notifier,
        channel=CHANNEL,
        broadcast_type=broadcast_type,
        reconnect_backoff_min=0.01,
        reconnect_backoff_max=0.05,
        resync_settle_seconds=0,
    )


# --- the backend on its own ---------------------------------------------------


@pytest.mark.asyncio
async def test_delivers_published_messages(redis_server_with_password):
    listener = ResilientRedisBackend(redis_server_with_password.url)
    publisher = ResilientRedisBackend(redis_server_with_password.url)
    await listener.connect()
    await publisher.connect()
    try:
        await listener.subscribe(CHANNEL)
        await _wait_for(lambda: CHANNEL in redis_server_with_password.channels())
        await publisher.publish(CHANNEL, "hello")
        event = await asyncio.wait_for(listener.next_published(), timeout=5)
        assert (event.channel, event.message) == (CHANNEL, "hello")
    finally:
        await listener.disconnect()
        await publisher.disconnect()


@pytest.mark.asyncio
async def test_lost_connection_is_reported_as_none(redis_server):
    # The broadcaster package reads None from next_published() as "backend
    # disconnected"; that is what hands control to the reconnect loop.
    backend = ResilientRedisBackend(redis_server.url)
    await backend.connect()
    try:
        await backend.subscribe(CHANNEL)
        await _wait_for(lambda: CHANNEL in redis_server.channels())
        await redis_server.stop()
        assert await asyncio.wait_for(backend.next_published(), timeout=5) is None
    finally:
        await backend.disconnect()


@pytest.mark.asyncio
async def test_unsubscribe_after_a_lost_connection_does_not_reconnect(redis_server):
    backend = ResilientRedisBackend(redis_server.url)
    await backend.connect()
    try:
        await backend.subscribe(CHANNEL)
        await _wait_for(lambda: CHANNEL in redis_server.channels())
        await redis_server.restart()
        assert await asyncio.wait_for(backend.next_published(), timeout=5) is None
        connections_before = redis_server.connections_accepted
        await backend.unsubscribe(CHANNEL)
        await asyncio.sleep(0.1)
        assert redis_server.connections_accepted == connections_before
    finally:
        await backend.disconnect()


@pytest.mark.asyncio
async def test_unsubscribing_is_not_reported_as_a_lost_connection(redis_server):
    backend = ResilientRedisBackend(redis_server.url)
    await backend.connect()
    try:
        await backend.subscribe(CHANNEL)
        await _wait_for(lambda: CHANNEL in redis_server.channels())
        await backend.unsubscribe(CHANNEL)
        await _wait_for(lambda: backend._reader_task.done())
        assert backend._queue.empty()
    finally:
        await backend.disconnect()


@pytest.mark.asyncio
async def test_connect_fails_while_redis_is_down(redis_server):
    await redis_server.stop()
    backend = ResilientRedisBackend(redis_server.url)
    with pytest.raises((RedisError, OSError)):
        await backend.connect()
    # Nothing is left open for the next attempt to leak.
    assert backend._client is None


@pytest.mark.asyncio
async def test_connect_fails_on_a_wrong_password(redis_server_with_password):
    wrong = redis_server_with_password.url.replace(PASSWORD, "not-the-password")
    backend = ResilientRedisBackend(wrong)
    with pytest.raises(RedisError):
        await backend.connect()
    assert backend._client is None


def test_keepalive_options_are_ones_this_platform_defines():
    options = tcp_keepalive_options()
    assert options, "expected at least one TCP keepalive option"
    assert all(isinstance(option, int) for option in options)
    assert all(value > 0 for value in options.values())


# --- which backend a URL gets --------------------------------------------------


@pytest.mark.parametrize("scheme", ["redis", "rediss"])
def test_redis_urls_get_the_resilient_backend(scheme):
    broadcast = ResilientBroadcast(f"{scheme}://:secret@redis.example:6380")
    backend = broadcast._backend
    assert isinstance(backend, ResilientRedisBackend)
    assert (backend._host, backend._port, backend._password) == (
        "redis.example",
        6380,
        "secret",
    )


def test_other_backbones_keep_their_stock_backend():
    broadcast = ResilientBroadcast("postgres://localhost/test")
    assert isinstance(broadcast._backend, PostgresBackend)


def _build_server(uri="redis://localhost"):
    # Builds the broadcaster object only; nothing connects until a reader starts.
    return OpalServer(
        init_policy_watcher=False,
        init_publisher=False,
        broadcaster_uri=uri,
        enable_jwks_endpoint=False,
    )


def test_server_uses_the_resilient_backend_by_default():
    broadcaster = _build_server().pubsub.broadcaster
    assert isinstance(broadcaster, ReconnectingBroadcaster)
    assert broadcaster._broadcast_type is ResilientBroadcast


def test_kill_switch_reverts_to_the_stock_backend(monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "BROADCAST_REDIS_RESILIENT_BACKEND_ENABLED", False
    )
    assert _build_server().pubsub.broadcaster._broadcast_type is Broadcast


def test_legacy_broadcaster_keeps_the_stock_backend(monkeypatch):
    # Without the reconnect loop nothing would act on the disconnect signal, so
    # the non-reconnecting broadcaster keeps the backend that reconnects itself.
    monkeypatch.setattr(opal_server_config, "BROADCAST_RECONNECT_ENABLED", False)
    broadcaster = _build_server().pubsub.broadcaster
    assert type(broadcaster) is EventBroadcaster
    assert broadcaster._broadcast_type is Broadcast


# --- the restart scenario, end to end -----------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("password", [PASSWORD, None], ids=["password", "no-password"])
async def test_listener_is_recreated_after_redis_restarts(password):
    server = await _start_server(password=password)
    notifier = RecordingNotifier()
    broadcaster = _reconnecting_broadcaster(server.url, notifier, ResilientBroadcast)
    resyncs = []

    async def on_reconnect():
        resyncs.append(broadcaster.backbone_gap_generation())

    broadcaster.set_reconnect_callback(on_reconnect)
    try:
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: CHANNEL in server.channels())

            await server.restart()

            # The listener is back ...
            await _wait_for(lambda: CHANNEL in server.channels())
            # ... the broadcaster knows there was a gap, so the resync fired ...
            await _wait_for(lambda: resyncs == [1])
            assert broadcaster.is_reader_healthy()
            assert not broadcaster.is_in_backbone_gap()

            # ... and a peer's broadcast reaches this server again.
            async with ResilientBroadcast(server.url) as peer:
                await peer.publish(
                    CHANNEL,
                    pydantic_serialize(
                        BroadcastNotification(
                            notifier_id="a-peer", topics=["policy_data"], data="v2"
                        )
                    ),
                )
            await _wait_for(lambda: notifier.notified == [(["policy_data"], "v2")])
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_negative_control_stock_backend_with_password_stays_deaf(
    redis_server_with_password,
):
    # The bug in #883: the stock backend reconnects inside asyncio-redis, which
    # refuses to send AUTH on a connection that is in pub/sub mode, so it never
    # subscribes again. The broadcaster sees no gap and still reports healthy.
    server = redis_server_with_password
    broadcaster = _reconnecting_broadcaster(server.url, RecordingNotifier(), Broadcast)
    async with broadcaster.get_listening_context():
        await _wait_for(lambda: CHANNEL in server.channels())
        connections_before = server.connections_accepted

        await server.restart()

        # asyncio-redis has reconnected both of its connections ...
        await _wait_for(
            lambda: server.connections_accepted >= connections_before + 2,
            timeout=15,
        )
        await asyncio.sleep(0.5)
        # ... but nothing listens, and nothing noticed.
        assert CHANNEL not in server.channels()
        assert broadcaster.backbone_gap_generation() == 0
        assert broadcaster.is_reader_healthy()


@pytest.mark.asyncio
async def test_negative_control_stock_backend_hides_the_gap(redis_server):
    # Without a password the stock backend does subscribe again, but out of
    # sight: no gap is recorded, so no resync reconciles what was missed.
    broadcaster = _reconnecting_broadcaster(
        redis_server.url, RecordingNotifier(), Broadcast
    )
    resyncs = []

    async def on_reconnect():
        resyncs.append(True)

    broadcaster.set_reconnect_callback(on_reconnect)
    async with broadcaster.get_listening_context():
        await _wait_for(lambda: CHANNEL in redis_server.channels())

        await redis_server.restart()

        await _wait_for(lambda: CHANNEL in redis_server.channels(), timeout=15)
        await asyncio.sleep(0.2)
        assert broadcaster.backbone_gap_generation() == 0
        assert resyncs == []
