"""The Redis broadcaster backend against a Redis stand-in on a real socket.

``FakeRedis`` speaks enough RESP2 for what the backend sends (AUTH, SELECT,
SUBSCRIBE, UNSUBSCRIBE, PUBLISH, PING), counts the connections it accepts and
records every command, and can fail the ways a Redis does: refuse, accept then
close or reset, drop every session, reject a password.
"""
import asyncio
import socket
import struct
import sys
from contextlib import suppress
from typing import Dict, List, Optional

import pytest
from broadcaster import Broadcast
from broadcaster._backends.postgres import PostgresBackend
from fastapi_websocket_pubsub import EventBroadcaster
from fastapi_websocket_pubsub.event_broadcaster import BroadcastNotification
from opal_common.tests.redaction_fixtures import capture_logs
from opal_server import broadcast_redis
from opal_server.broadcast_redis import (
    EndOnLossBroadcast,
    RedisBroadcastBackend,
    ResubscribingBroadcast,
    check_redis_url,
    connection_options,
)
from opal_server.config import opal_server_config
from opal_server.pubsub import PubSub
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from redis.asyncio.client import PubSub as RedisPubSub
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError


def _bulk(value: str) -> bytes:
    data = value.encode()
    return b"$%d\r\n%s\r\n" % (len(data), data)


def _array(*items: bytes) -> bytes:
    return b"*%d\r\n" % len(items) + b"".join(items)


def _integer(value: int) -> bytes:
    return b":%d\r\n" % value


async def _read_command(reader: asyncio.StreamReader) -> Optional[List[str]]:
    line = await reader.readline()
    if not line:
        return None
    count = int(line[1:])
    args = []
    for _ in range(count):
        header = await reader.readline()
        data = await reader.readexactly(int(header[1:]) + 2)
        args.append(data[:-2].decode())
    return args


class _Session:
    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer
        self.commands: List[List[str]] = []
        self.channels: set = set()
        self.authed = False


class FakeRedis:
    """A Redis stand-in on 127.0.0.1.

    ``users`` maps a user name to its password (``"default"`` is the user a
    one-argument AUTH names); with no users every command is allowed.
    ``on_accept`` is ``"serve"``, ``"close"`` (close at once) or ``"reset"``
    (close with an RST).
    """

    def __init__(self, users: Optional[Dict[str, str]] = None):
        self.users = users or {}
        self.on_accept = "serve"
        self.accepts = 0
        self.sessions: List[_Session] = []
        self.closed_sessions: List[_Session] = []
        self.published: List[tuple] = []
        self._server: Optional[asyncio.AbstractServer] = None
        self.port = 0

    @property
    def subscribes(self) -> int:
        return sum(
            1
            for session in self.sessions + self.closed_sessions
            for command in session.commands
            if command[0].upper() == "SUBSCRIBE"
        )

    def url(self, userinfo: str = "") -> str:
        at = f"{userinfo}@" if userinfo else ""
        return f"redis://{at}127.0.0.1:{self.port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.drop()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    def drop(self) -> None:
        """Close every open session, as a Redis restart does."""
        for session in list(self.sessions):
            session.writer.close()

    def push(self, channel: str, message: str) -> int:
        """Deliver a message on ``channel``, as another server's PUBLISH
        does."""
        receivers = [s for s in self.sessions if channel in s.channels]
        for session in receivers:
            session.writer.write(
                _array(_bulk("message"), _bulk(channel), _bulk(message))
            )
        return len(receivers)

    async def __aenter__(self) -> "FakeRedis":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    async def _serve(self, reader, writer) -> None:
        self.accepts += 1
        if self.on_accept == "reset":
            sock = writer.get_extra_info("socket")
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
            )
            writer.close()
            return
        if self.on_accept == "close":
            writer.close()
            return
        session = _Session(writer)
        self.sessions.append(session)
        try:
            while True:
                command = await _read_command(reader)
                if command is None:
                    break
                session.commands.append(command)
                writer.write(self._answer(session, command))
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.sessions.remove(session)
            self.closed_sessions.append(session)
            writer.close()

    def _answer(self, session: _Session, command: List[str]) -> bytes:
        name, args = command[0].upper(), command[1:]
        if name == "AUTH":
            user, password = ("default", args[0]) if len(args) == 1 else args
            if self.users.get(user) == password:
                session.authed = True
                return b"+OK\r\n"
            return b"-WRONGPASS invalid username-password pair or user is disabled.\r\n"
        if self.users and not session.authed:
            return b"-NOAUTH Authentication required.\r\n"
        if name == "SUBSCRIBE":
            replies = []
            for channel in args:
                session.channels.add(channel)
                replies.append(
                    _array(
                        _bulk("subscribe"),
                        _bulk(channel),
                        _integer(len(session.channels)),
                    )
                )
            return b"".join(replies)
        if name == "UNSUBSCRIBE":
            replies = []
            for channel in args or sorted(session.channels):
                session.channels.discard(channel)
                replies.append(
                    _array(
                        _bulk("unsubscribe"),
                        _bulk(channel),
                        _integer(len(session.channels)),
                    )
                )
            return b"".join(replies)
        if name == "PUBLISH":
            self.published.append((args[0], args[1]))
            return _integer(self.push(args[0], args[1]))
        if name == "PING":
            if session.channels:
                return _array(_bulk("pong"), _bulk(args[0] if args else ""))
            return b"+PONG\r\n"
        if name in ("SELECT", "CLIENT"):
            return b"+OK\r\n"
        return b"-ERR unknown command\r\n"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Notifier:
    def __init__(self):
        self.notified = []

    async def notify(self, topics, data, notifier_id=None):
        self.notified.append((list(topics), data))

    async def subscribe(self, *args, **kwargs):
        pass

    async def unsubscribe(self, *args, **kwargs):
        pass


def _notification(data, topic="policy_data") -> str:
    return BroadcastNotification(
        notifier_id="another-server", topics=[topic], data=data
    ).model_dump_json()


def _reconnecting(url: str, notifier=None, **kwargs) -> ReconnectingBroadcaster:
    kwargs.setdefault("reconnect_backoff_min", 0)
    kwargs.setdefault("reconnect_backoff_max", 0)
    kwargs.setdefault("resync_settle_seconds", 0)
    return ReconnectingBroadcaster(
        url,
        notifier=notifier or _Notifier(),
        channel="EventNotifier",
        broadcast_type=EndOnLossBroadcast,
        **kwargs,
    )


async def _wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.01)


async def _stop(task: asyncio.Task) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_a_dropped_pubsub_connection_raises_and_is_not_resubscribed():
    """With the options the backend gives redis-py, a lost subscriber
    connection raises from get_message, and redis-py itself sends no second
    SUBSCRIBE."""
    async with FakeRedis() as fake:
        pool = ConnectionPool(**connection_options(fake.url()))
        pubsub = RedisPubSub(pool)
        try:
            await pubsub.subscribe("EventNotifier")
            assert (await pubsub.get_message(timeout=1))["type"] == "subscribe"
            fake.drop()
            with pytest.raises(RedisConnectionError):
                await pubsub.get_message(timeout=1)
            await asyncio.sleep(0.2)
            assert fake.subscribes == 1
            assert fake.accepts == 1
        finally:
            await pubsub.reset()
            await pool.disconnect()


@pytest.mark.asyncio
async def test_a_publish_reaches_a_subscriber_on_another_connection():
    async with FakeRedis() as fake:
        async with EndOnLossBroadcast(fake.url()) as reader:
            async with reader.subscribe("EventNotifier") as subscriber:
                async with EndOnLossBroadcast(fake.url()) as writer:
                    await writer.publish("EventNotifier", "hello")
                event = await asyncio.wait_for(subscriber.get(), 2)
    assert (event.channel, event.message) == ("EventNotifier", "hello")
    assert fake.published == [("EventNotifier", "hello")]


@pytest.mark.asyncio
async def test_the_subscriber_ends_when_its_connection_drops():
    async with FakeRedis() as fake:
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            async with broadcast.subscribe("EventNotifier") as subscriber:
                fake.drop()
                events = [
                    event async for event in _with_timeout(subscriber.__aiter__(), 2)
                ]
    assert events == []


async def _with_timeout(iterator, seconds):
    async with asyncio.timeout(seconds):
        async for item in iterator:
            yield item


@pytest.mark.asyncio
async def test_next_published_returns_none_after_a_loss_and_keeps_returning_none():
    async with FakeRedis() as fake:
        backend = RedisBroadcastBackend(fake.url())
        await backend.connect()
        try:
            await backend.subscribe("EventNotifier")
            fake.drop()
            assert await asyncio.wait_for(backend.next_published(), 2) is None
            assert await asyncio.wait_for(backend.next_published(), 2) is None
            assert fake.subscribes == 1
        finally:
            await backend.disconnect()


@pytest.mark.parametrize("on_accept", ["close", "reset"])
@pytest.mark.asyncio
async def test_a_redis_that_accepts_then_drops_is_retried_with_backoff(on_accept):
    """Each attempt waits at least half the backoff (equal jitter), so one
    second at 0.2 s allows at most 10 attempts of at most two connections each;
    the library's own reconnect loop made thousands."""
    async with FakeRedis() as fake:
        fake.on_accept = on_accept
        broadcaster = _reconnecting(
            fake.url(), reconnect_backoff_min=0.2, reconnect_backoff_max=0.2
        )
        task = await broadcaster.start_reader_task()
        await asyncio.sleep(1.0)
        await _stop(task)
    assert 2 <= fake.accepts <= 2 * 11


@pytest.mark.parametrize("on_accept", ["close", "reset"])
@pytest.mark.asyncio
async def test_a_redis_that_accepts_then_drops_counts_toward_max_retries(on_accept):
    gave_up = []
    async with FakeRedis() as fake:
        fake.on_accept = on_accept
        broadcaster = _reconnecting(fake.url(), reconnect_max_retries=3)
        broadcaster.set_give_up_callback(lambda: _record(gave_up))
        task = await broadcaster.start_reader_task()
        await asyncio.wait_for(task, 5)
    assert task.exception() is None
    assert gave_up == [True]
    assert 3 <= fake.accepts <= 2 * 3


async def _record(calls: list) -> None:
    calls.append(True)


@pytest.mark.asyncio
async def test_a_refused_redis_counts_toward_max_retries():
    gave_up = []
    broadcaster = _reconnecting(
        f"redis://127.0.0.1:{_free_port()}", reconnect_max_retries=3
    )
    broadcaster.set_give_up_callback(lambda: _record(gave_up))
    with capture_logs() as logs:
        task = await broadcaster.start_reader_task()
        await asyncio.wait_for(task, 5)
    assert gave_up == [True]
    assert "Broadcaster listener error (attempt 3)" in "".join(logs.text)


@pytest.mark.asyncio
async def test_a_dropped_session_is_one_gap_with_one_resync():
    notifier = _Notifier()
    resyncs = []
    async with FakeRedis() as fake:
        broadcaster = _reconnecting(fake.url(), notifier=notifier)
        broadcaster.set_reconnect_callback(lambda: _record(resyncs))
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: fake.subscribes == 1 and fake.sessions)
            await _wait_for(lambda: fake.push("EventNotifier", _notification(1)))
            await _wait_for(lambda: len(notifier.notified) == 1)

            fake.drop()
            await _wait_for(lambda: resyncs == [True])
            assert fake.subscribes == 2

            await _wait_for(lambda: fake.push("EventNotifier", _notification(2)))
            await _wait_for(lambda: len(notifier.notified) == 2)
            assert broadcaster.is_reader_healthy()
    assert [data for _, data in notifier.notified] == [1, 2]
    assert resyncs == [True]


@pytest.mark.asyncio
async def test_a_redis_restart_is_a_gap_with_a_resync():
    resyncs = []
    async with FakeRedis() as fake:
        broadcaster = _reconnecting(
            fake.url(), reconnect_backoff_min=0.05, reconnect_backoff_max=0.05
        )
        broadcaster.set_reconnect_callback(lambda: _record(resyncs))
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: fake.subscribes == 1 and fake.sessions)
            await _wait_for(lambda: fake.push("EventNotifier", _notification(1)))
            await fake.stop()
            await asyncio.sleep(0.2)
            await fake.start()
            await _wait_for(lambda: resyncs == [True])
    assert fake.subscribes == 2


@pytest.mark.parametrize(
    "userinfo, users, auth",
    [
        (":p%25ss%40word", {"default": "p%ss@word"}, ["AUTH", "p%ss@word"]),
        ("opal:p%25ss", {"opal": "p%ss"}, ["AUTH", "opal", "p%ss"]),
    ],
    ids=["password", "acl-user"],
)
@pytest.mark.asyncio
async def test_every_reconnect_authenticates_before_it_subscribes(
    userinfo, users, auth
):
    async with FakeRedis(users=users) as fake:
        broadcaster = _reconnecting(fake.url(userinfo))
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: fake.subscribes == 1 and fake.sessions)
            fake.drop()
            await _wait_for(lambda: fake.subscribes == 2 and fake.sessions)
        sessions = fake.closed_sessions + fake.sessions
    subscribed = [s for s in sessions if ["SUBSCRIBE", "EventNotifier"] in s.commands]
    assert len(subscribed) == 2
    for session in subscribed:
        assert session.commands[0] == auth
        assert session.commands.index(["SUBSCRIBE", "EventNotifier"]) > 0


@pytest.mark.asyncio
async def test_a_refused_subscription_is_a_counted_attempt_with_its_reason():
    gave_up = []
    async with FakeRedis(users={"default": "secret"}) as fake:
        broadcaster = _reconnecting(fake.url(), reconnect_max_retries=2)
        broadcaster.set_give_up_callback(lambda: _record(gave_up))
        with capture_logs() as logs:
            task = await broadcaster.start_reader_task()
            await asyncio.wait_for(task, 5)
    assert gave_up == [True]
    errors = [line for line in logs.text if "Broadcaster listener error" in line]
    assert len(errors) == 2
    assert all("Authentication required" in line for line in errors)


@pytest.mark.asyncio
async def test_a_wrong_password_is_a_counted_attempt_and_is_not_logged():
    gave_up = []
    async with FakeRedis(users={"default": "right"}) as fake:
        broadcaster = _reconnecting(fake.url(":wrong-secret"), reconnect_max_retries=2)
        broadcaster.set_give_up_callback(lambda: _record(gave_up))
        with capture_logs() as logs:
            task = await broadcaster.start_reader_task()
            await asyncio.wait_for(task, 5)
    text = "".join(logs.text)
    assert gave_up == [True]
    assert "invalid username-password pair" in text
    assert "wrong-secret" not in text


# The stock EventBroadcaster parses each incoming broadcast with pydantic's V1 API.
@pytest.mark.filterwarnings("ignore:The `parse_raw` method is deprecated")
@pytest.mark.filterwarnings("ignore:`load_str_bytes` is deprecated")
@pytest.mark.asyncio
async def test_the_stock_broadcaster_resubscribes_with_backoff(monkeypatch):
    """With OPAL_BROADCAST_RECONNECT_ENABLED off nothing above the backend
    reconnects, so the backend reopens its connection and subscribes again,
    backing off while Redis is away."""
    monkeypatch.setattr(broadcast_redis, "RESUBSCRIBE_BACKOFF_MIN_SECONDS", 0.2)
    monkeypatch.setattr(broadcast_redis, "RESUBSCRIBE_BACKOFF_MAX_SECONDS", 0.2)
    notifier = _Notifier()
    async with FakeRedis() as fake:
        broadcaster = EventBroadcaster(
            fake.url(),
            notifier=notifier,
            channel="EventNotifier",
            broadcast_type=ResubscribingBroadcast,
        )
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: fake.subscribes == 1 and fake.sessions)
            fake.on_accept = "close"
            fake.drop()
            await asyncio.sleep(1.0)
            assert 2 <= fake.accepts - 1 <= 2 * 10
            fake.on_accept = "serve"
            await _wait_for(lambda: fake.subscribes == 2 and fake.sessions)
            await _wait_for(lambda: fake.push("EventNotifier", _notification(3)))
            await _wait_for(lambda: notifier.notified)
            assert not broadcaster.get_reader_task().done()
    assert notifier.notified == [(["policy_data"], 3)]


@pytest.mark.parametrize("attempt", [0, 1, 6, 1023, 1024, 100_000])
def test_the_resubscribe_backoff_stays_within_its_bounds(attempt):
    """However long Redis stays away, the wait is between half the cap and the
    cap once the cap is reached."""
    delay = broadcast_redis._resubscribe_backoff_seconds(attempt)
    assert 0 < delay <= broadcast_redis.RESUBSCRIBE_BACKOFF_MAX_SECONDS
    if attempt >= 6:
        assert delay >= broadcast_redis.RESUBSCRIBE_BACKOFF_MAX_SECONDS / 2


@pytest.mark.asyncio
async def test_the_backend_needs_no_asyncio_redis(monkeypatch):
    monkeypatch.setitem(sys.modules, "asyncio_redis", None)
    async with FakeRedis() as fake:
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            await broadcast.publish("EventNotifier", "hello")
    assert fake.published == [("EventNotifier", "hello")]


def test_other_schemes_keep_the_library_backends():
    broadcast = EndOnLossBroadcast("postgres://opal@localhost/opal")
    assert isinstance(broadcast._backend, PostgresBackend)


def test_a_redis_broadcast_has_what_the_library_broadcast_has():
    redis_broadcast = EndOnLossBroadcast("redis://localhost")
    library_broadcast = Broadcast("memory://")
    assert set(vars(redis_broadcast)) == set(vars(library_broadcast))
    assert isinstance(redis_broadcast._backend, RedisBroadcastBackend)


def test_the_url_cannot_turn_the_clients_own_retries_on():
    options = connection_options("redis://localhost:6379?retry_on_timeout=yes")
    connection = ConnectionPool(**options).make_connection()
    assert connection.retry_on_timeout is False
    assert connection.retry._retries == 0


@pytest.mark.parametrize("scheme", ["redis", "rediss"])
def test_an_unknown_url_parameter_is_refused_at_startup(scheme):
    with pytest.raises(ValueError, match="no_such_option"):
        check_redis_url(f"{scheme}://localhost:6379/0?no_such_option=1")


def test_a_known_url_parameter_is_accepted():
    check_redis_url("redis://user:pass@localhost:6379/2?client_name=opal")


@pytest.mark.parametrize(
    "reconnect, expected", [(True, EndOnLossBroadcast), (False, ResubscribingBroadcast)]
)
def test_the_server_picks_the_broadcast_type_for_its_reader(
    monkeypatch, reconnect, expected
):
    monkeypatch.setattr(opal_server_config, "BROADCAST_RECONNECT_ENABLED", reconnect)
    pubsub = PubSub(signer=object(), broadcaster_uri="redis://localhost:6379")
    assert pubsub.broadcaster._broadcast_type is expected


def test_the_server_refuses_an_unknown_redis_url_parameter():
    with pytest.raises(ValueError, match="no_such_option"):
        PubSub(signer=object(), broadcaster_uri="redis://localhost?no_such_option=1")


def test_the_legacy_redis_reader_says_it_has_no_gap_resync(monkeypatch):
    monkeypatch.setattr(opal_server_config, "BROADCAST_RECONNECT_ENABLED", False)
    with capture_logs() as logs:
        PubSub(signer=object(), broadcaster_uri="redis://localhost:6379")
    assert "no resync after a lost Redis connection" in "".join(logs.text)


def test_a_postgres_server_logs_no_redis_line(monkeypatch):
    monkeypatch.setattr(opal_server_config, "BROADCAST_RECONNECT_ENABLED", False)
    with capture_logs() as logs:
        PubSub(signer=object(), broadcaster_uri="postgres://opal@localhost/opal")
    assert "Redis" not in "".join(logs.text)
