"""The Redis broadcaster backend against a Redis stand-in on a real socket.

``FakeRedis`` speaks enough RESP2 for what the backend sends (AUTH, SELECT,
SUBSCRIBE, UNSUBSCRIBE, PUBLISH, PING), counts the connections it accepts and
records every command, and can fail the ways a Redis does: refuse, accept then
close or reset, drop every session, reject a password, or leave a command
unanswered. It serves TLS when given a server context, and records what a
client that does not speak RESP sends.
"""
import asyncio
import datetime
import ipaddress
import socket
import ssl
import struct
import sys
from contextlib import suppress
from pathlib import Path
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
from redis.exceptions import TimeoutError as RedisTimeoutError


def _bulk(value: str) -> bytes:
    data = value.encode()
    return b"$%d\r\n%s\r\n" % (len(data), data)


def _array(*items: bytes) -> bytes:
    return b"*%d\r\n" % len(items) + b"".join(items)


def _integer(value: int) -> bytes:
    return b":%d\r\n" % value


async def _read_command(reader: asyncio.StreamReader) -> Optional[List[str]]:
    """Read one command, its leading ``*`` already read."""
    line = await reader.readline()
    if not line:
        return None
    count = int(line)
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
    ``on_accept`` is ``"serve"``, ``"close"`` (close at once), ``"reset"``
    (close with an RST) or ``"silent"`` (read nothing, answer nothing).
    Commands named in ``mute`` are recorded and never answered. With ``tls``
    (a server SSL context) every connection is TLS.
    """

    def __init__(
        self,
        users: Optional[Dict[str, str]] = None,
        tls: Optional[ssl.SSLContext] = None,
    ):
        self.users = users or {}
        self.tls = tls
        self.on_accept = "serve"
        self.mute: set = set()
        self.raw: List[bytes] = []
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

    def count(self, name: str) -> int:
        """How many commands called ``name`` Redis received."""
        return sum(
            1
            for session in self.sessions + self.closed_sessions
            for command in session.commands
            if command[0].upper() == name
        )

    def url(self, userinfo: str = "") -> str:
        at = f"{userinfo}@" if userinfo else ""
        return f"redis://{at}127.0.0.1:{self.port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._serve, "127.0.0.1", self.port, ssl=self.tls
        )
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
        await broadcast_redis.close_shared_pools()
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
        if self.on_accept == "silent":
            self.sessions.append(session)
            with suppress(ConnectionError):
                await reader.read()
            self.sessions.remove(session)
            writer.close()
            return
        self.sessions.append(session)
        try:
            while True:
                first = await reader.read(1)
                if first != b"*":
                    self.raw.append(first + await reader.read(65536))
                    break
                command = await _read_command(reader)
                if command is None:
                    break
                session.commands.append(command)
                if command[0].upper() in self.mute:
                    continue
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


def _self_signed(directory: Path) -> Path:
    """A self-signed certificate for 127.0.0.1 in ``directory``, its PEM
    path."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "another CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "cert.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path


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


class _Subscription:
    """What the broadcaster's sharing callback is handed for a local
    publish."""

    def __init__(self, topic: str):
        self.topic = topic


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


@pytest.fixture
def short_timeouts(monkeypatch):
    """The backend's fixed timeouts, shortened so a test waits a fraction of a
    second instead of 10 to 25."""
    monkeypatch.setattr(broadcast_redis, "CONNECT_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(broadcast_redis, "PUBLISH_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(broadcast_redis, "PING_INTERVAL_SECONDS", 0.3)
    monkeypatch.setattr(broadcast_redis, "PING_TIMEOUT_SECONDS", 0.2)


@pytest.mark.asyncio
async def test_a_redis_silent_at_auth_is_a_counted_attempt(short_timeouts):
    gave_up = []
    async with FakeRedis(users={"default": "secret"}) as fake:
        fake.mute.add("AUTH")
        broadcaster = _reconnecting(fake.url(":secret"), reconnect_max_retries=2)
        broadcaster.set_give_up_callback(lambda: _record(gave_up))
        with capture_logs() as logs:
            task = await broadcaster.start_reader_task()
            await asyncio.wait_for(task, 5)
    assert gave_up == [True]
    errors = [line for line in logs.text if "Broadcaster listener error" in line]
    assert len(errors) == 2
    assert all("did not connect" in line for line in errors)


@pytest.mark.asyncio
async def test_a_redis_silent_at_subscribe_is_a_counted_attempt(short_timeouts):
    gave_up = []
    async with FakeRedis() as fake:
        fake.mute.add("SUBSCRIBE")
        broadcaster = _reconnecting(fake.url(), reconnect_max_retries=2)
        broadcaster.set_give_up_callback(lambda: _record(gave_up))
        with capture_logs() as logs:
            task = await broadcaster.start_reader_task()
            await asyncio.wait_for(task, 5)
    assert gave_up == [True]
    errors = [line for line in logs.text if "Broadcaster listener error" in line]
    assert len(errors) == 2
    assert all("did not confirm SUBSCRIBE" in line for line in errors)


@pytest.mark.asyncio
async def test_a_quiet_healthy_subscription_is_kept_alive_by_ping(short_timeouts):
    resyncs = []
    async with FakeRedis() as fake:
        broadcaster = _reconnecting(fake.url())
        broadcaster.set_reconnect_callback(lambda: _record(resyncs))
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: fake.subscribes == 1 and fake.sessions)
            await asyncio.sleep(1.5)
            pings = fake.count("PING")
    assert pings >= 2
    assert resyncs == []
    assert fake.accepts == 1


@pytest.mark.asyncio
async def test_a_redis_that_goes_silent_mid_session_is_a_gap(short_timeouts):
    """No answer to PING within the timeout is a lost connection: the
    reader reconnects and resyncs, as after a dropped session."""
    resyncs = []
    async with FakeRedis() as fake:
        broadcaster = _reconnecting(fake.url())
        broadcaster.set_reconnect_callback(lambda: _record(resyncs))
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: fake.subscribes == 1 and fake.sessions)
            await _wait_for(lambda: fake.push("EventNotifier", _notification(1)))
            fake.mute.add("PING")
            started = asyncio.get_running_loop().time()
            await _wait_for(lambda: fake.subscribes == 2)
            lost_after = asyncio.get_running_loop().time() - started
            fake.mute.discard("PING")
            await _wait_for(lambda: resyncs == [True])
    # interval (0.3) + PING timeout (0.2), and less than the 1 s it would
    # take with no PING at all
    assert lost_after < 1.0


@pytest.mark.asyncio
async def test_a_publish_that_never_completes_fails_into_the_replay_buffer(
    short_timeouts, monkeypatch
):
    """The publish's own limit fails it, well before the connection's socket
    timeouts would."""
    monkeypatch.setattr(broadcast_redis, "CONNECT_TIMEOUT_SECONDS", 5.0)
    async with FakeRedis() as fake:
        broadcaster = _reconnecting(fake.url())
        fake.mute.add("PUBLISH")
        started = asyncio.get_running_loop().time()
        with capture_logs() as logs:
            await broadcaster.__broadcast_notifications__(
                _Subscription("policy_data"), {"x": 1}
            )
        took = asyncio.get_running_loop().time() - started
        assert list(broadcaster._outbound_buffer) == [("policy_data", {"x": 1})]
    assert 0.3 <= took < 1.0
    assert "buffered for replay" in "".join(logs.text)


@pytest.mark.asyncio
async def test_every_redis_connection_has_tcp_keepalive():
    async with FakeRedis() as fake:
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            async with broadcast.subscribe("EventNotifier"):
                connection = broadcast._backend._pubsub.connection
                sock = connection._writer.get_extra_info("socket")
                assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
                idle = getattr(socket, "TCP_KEEPIDLE", None) or socket.TCP_KEEPALIVE
                assert sock.getsockopt(socket.IPPROTO_TCP, idle) == 30
                assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL) == 10
                assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT) == 3


def test_the_url_cannot_change_the_timeouts_or_the_keepalive():
    options = connection_options(
        "redis://localhost:6379?socket_timeout=600&socket_keepalive=no"
        "&health_check_interval=1"
    )
    connection = ConnectionPool(**options).make_connection()
    assert connection.socket_timeout == broadcast_redis.CONNECT_TIMEOUT_SECONDS
    assert connection.socket_connect_timeout == broadcast_redis.CONNECT_TIMEOUT_SECONDS
    assert connection.socket_keepalive is True
    assert connection.health_check_interval == 0


def _rediss_url(fake: FakeRedis, query: str = "", host: str = "127.0.0.1") -> str:
    return f"rediss://{host}:{fake.port}" + (f"?{query}" if query else "")


@pytest.mark.asyncio
async def test_rediss_publishes_and_subscribes_over_tls(tls_cert):
    async with FakeRedis(tls=tls_cert.context) as fake:
        url = _rediss_url(fake, f"ssl_ca_certs={tls_cert.path}")
        async with EndOnLossBroadcast(url) as reader:
            async with reader.subscribe("EventNotifier") as subscriber:
                async with EndOnLossBroadcast(url) as writer:
                    await writer.publish("EventNotifier", "hello")
                event = await asyncio.wait_for(subscriber.get(), 2)
    assert event.message == "hello"
    assert fake.accepts >= 2


@pytest.mark.asyncio
async def test_rediss_authenticates_inside_tls(tls_cert):
    async with FakeRedis(users={"default": "secret"}, tls=tls_cert.context) as fake:
        url = f"rediss://:secret@127.0.0.1:{fake.port}?ssl_ca_certs={tls_cert.path}"
        async with EndOnLossBroadcast(url) as broadcast:
            await broadcast.publish("EventNotifier", "hello")
    assert fake.published == [("EventNotifier", "hello")]


@pytest.mark.asyncio
async def test_rediss_with_a_ca_that_did_not_sign_the_certificate_fails_closed(
    tls_cert, tmp_path
):
    other_ca = _self_signed(tmp_path / "other")
    gave_up = []
    async with FakeRedis(users={"default": "secret"}, tls=tls_cert.context) as fake:
        broadcaster = _reconnecting(
            f"rediss://:secret@127.0.0.1:{fake.port}?ssl_ca_certs={other_ca}",
            reconnect_max_retries=2,
        )
        broadcaster.set_give_up_callback(lambda: _record(gave_up))
        with capture_logs() as logs:
            task = await broadcaster.start_reader_task()
            await asyncio.wait_for(task, 5)
    assert gave_up == [True]
    assert "CERTIFICATE_VERIFY_FAILED" in "".join(logs.text)
    assert fake.count("AUTH") == 0


@pytest.mark.asyncio
async def test_rediss_checks_the_host_name(tls_cert):
    """The test certificate names 127.0.0.1 only, so connecting by the name
    localhost must fail even though the CA is trusted."""
    async with FakeRedis(tls=tls_cert.context) as fake:
        url = _rediss_url(fake, f"ssl_ca_certs={tls_cert.path}", host="localhost")
        with pytest.raises(RedisConnectionError, match="match|mismatch"):
            async with EndOnLossBroadcast(url):
                pass
    assert fake.count("PING") == 0


@pytest.mark.asyncio
async def test_rediss_without_a_ca_uses_the_system_trust_store(tls_cert):
    async with FakeRedis(tls=tls_cert.context) as fake:
        with pytest.raises(RedisConnectionError, match="CERTIFICATE_VERIFY_FAILED"):
            async with EndOnLossBroadcast(_rediss_url(fake)):
                pass


@pytest.mark.asyncio
async def test_rediss_to_a_redis_without_tls_sends_no_command(short_timeouts):
    async with FakeRedis(users={"default": "secret"}) as fake:
        url = f"rediss://:secret@127.0.0.1:{fake.port}"
        with pytest.raises((RedisConnectionError, RedisTimeoutError)):
            async with EndOnLossBroadcast(url):
                pass
        await _wait_for(lambda: fake.raw)
    assert fake.count("AUTH") == 0
    assert all(b"secret" not in data for data in fake.raw)


@pytest.mark.asyncio
async def test_a_tls_handshake_that_never_completes_times_out(tls_cert, short_timeouts):
    async with FakeRedis() as fake:
        fake.on_accept = "silent"
        url = _rediss_url(fake, f"ssl_ca_certs={tls_cert.path}")
        started = asyncio.get_running_loop().time()
        with pytest.raises(RedisTimeoutError, match="did not connect"):
            async with EndOnLossBroadcast(url):
                pass
        took = asyncio.get_running_loop().time() - started
    assert took < 1.0


@pytest.mark.parametrize(
    "query, warned",
    [
        ("", False),
        ("ssl_check_hostname=false", True),
        ("ssl_cert_reqs=none&ssl_check_hostname=false", True),
    ],
    ids=["verified", "host-name-off", "certificate-off"],
)
def test_turning_tls_verification_off_is_a_startup_warning(query, warned):
    with capture_logs() as logs:
        check_redis_url(f"rediss://:secret@localhost:6380?{query}")
    warnings = [line for line in logs.text if "WARNING" in line]
    assert bool(warnings) is warned
    assert all("does not verify" in line for line in warnings)
    assert all("secret" not in line for line in warnings)


@pytest.mark.parametrize(
    "query, problem",
    [
        ("ssl_ca_certs=/no/such/ca.pem", "No such file"),
        ("ssl_cert_reqs=none", "check_hostname"),
    ],
)
def test_unusable_tls_settings_are_refused_at_startup(query, problem):
    with pytest.raises(ValueError, match=problem):
        check_redis_url(f"rediss://localhost:6380?{query}")


@pytest.mark.asyncio
async def test_publishes_reuse_one_connection():
    async with FakeRedis(users={"default": "secret"}) as fake:
        for number in range(10):
            async with EndOnLossBroadcast(fake.url(":secret")) as broadcast:
                await broadcast.publish("EventNotifier", str(number))
    assert len(fake.published) == 10
    assert fake.accepts == 1
    assert fake.count("AUTH") == 1


@pytest.mark.asyncio
async def test_concurrent_publishes_open_at_most_the_pool_size():
    async def publish(number: int) -> None:
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            await broadcast.publish("EventNotifier", str(number))

    async with FakeRedis() as fake:
        await asyncio.gather(*(publish(number) for number in range(30)))
    assert sorted(int(message) for _, message in fake.published) == list(range(30))
    assert fake.accepts <= broadcast_redis.POOL_MAX_CONNECTIONS


@pytest.mark.asyncio
async def test_the_reader_and_the_publishes_share_the_pool():
    async with FakeRedis() as fake:
        async with EndOnLossBroadcast(fake.url()) as reader:
            async with reader.subscribe("EventNotifier") as subscriber:
                for number in range(5):
                    async with EndOnLossBroadcast(fake.url()) as writer:
                        await writer.publish("EventNotifier", str(number))
                    await asyncio.wait_for(subscriber.get(), 2)
    assert fake.accepts == 2


@pytest.mark.asyncio
async def test_a_publish_after_redis_closed_the_idle_connection_succeeds():
    async with FakeRedis() as fake:
        broadcaster = _reconnecting(fake.url())
        await broadcaster.__broadcast_notifications__(
            _Subscription("policy_data"), {"x": 1}
        )
        fake.drop()
        await _wait_for(lambda: not fake.sessions)
        await broadcaster.__broadcast_notifications__(
            _Subscription("policy_data"), {"x": 2}
        )
        assert list(broadcaster._outbound_buffer) == []
    assert len(fake.published) == 2
    assert fake.accepts == 2


@pytest.mark.asyncio
async def test_each_url_has_its_own_pool():
    async with FakeRedis(users={"opal": "one", "other": "two"}) as fake:
        for userinfo in ("opal:one", "other:two", "opal:one"):
            async with EndOnLossBroadcast(fake.url(userinfo)) as broadcast:
                await broadcast.publish("EventNotifier", userinfo)
    assert fake.accepts == 2
    assert fake.count("AUTH") == 2


@pytest.mark.asyncio
async def test_a_connection_whose_auth_timed_out_is_not_reused(short_timeouts):
    """A pooled connection cut off in the middle of AUTH must not go back to
    the pool as if it were authenticated."""
    async with FakeRedis(users={"default": "secret"}) as fake:
        fake.mute.add("AUTH")
        with pytest.raises(RedisTimeoutError, match="did not connect"):
            async with EndOnLossBroadcast(fake.url(":secret")):
                pass
        fake.mute.clear()
        async with EndOnLossBroadcast(fake.url(":secret")) as broadcast:
            await broadcast.publish("EventNotifier", "hello")
    assert fake.published == [("EventNotifier", "hello")]
    assert fake.count("PUBLISH") == 1


class _FreezingProxy:
    """A TCP proxy in front of a Redis stand-in.

    ``freeze`` stops forwarding on the connections open at the time, in
    both directions, without closing them: a network path that went silent.
    """

    def __init__(self, target_port: int):
        self.target_port = target_port
        self.port = 0
        self._frozen: List[asyncio.Event] = []
        self._server: Optional[asyncio.AbstractServer] = None
        self._writers: List[asyncio.StreamWriter] = []

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for writer in self._writers:
            writer.close()
        self._server.close()
        await self._server.wait_closed()

    def freeze(self) -> None:
        for frozen in self._frozen:
            frozen.set()

    async def _handle(self, client_reader, client_writer) -> None:
        server_reader, server_writer = await asyncio.open_connection(
            "127.0.0.1", self.target_port
        )
        self._writers += [client_writer, server_writer]
        frozen = asyncio.Event()
        self._frozen.append(frozen)

        async def pipe(reader, writer):
            with suppress(ConnectionError):
                while data := await reader.read(65536):
                    if frozen.is_set():
                        await asyncio.Future()
                    writer.write(data)
                    await writer.drain()

        with suppress(asyncio.CancelledError):
            await asyncio.gather(
                pipe(client_reader, server_writer), pipe(server_reader, client_writer)
            )


@pytest.mark.asyncio
async def test_rediss_subscribers_lost_to_silence_return_their_connections(
    tls_cert, short_timeouts, monkeypatch
):
    """Closing a TLS connection to a silent peer would wait for its answer; the
    subscriber's connection must go back to the shared pool anyway, or the pool
    runs dry while Redis is healthy."""
    monkeypatch.setattr(broadcast_redis, "POOL_MAX_CONNECTIONS", 2)
    async with FakeRedis(tls=tls_cert.context) as fake:
        proxy = _FreezingProxy(fake.port)
        await proxy.start()
        url = f"rediss://127.0.0.1:{proxy.port}?ssl_ca_certs={tls_cert.path}"
        try:
            for _ in range(3):
                backend = RedisBroadcastBackend(url)
                await backend.connect()
                await backend.subscribe("EventNotifier")
                proxy.freeze()
                assert await asyncio.wait_for(backend.next_published(), 5) is None
                await backend.disconnect()
            async with EndOnLossBroadcast(url) as broadcast:
                await broadcast.publish("EventNotifier", "after")
        finally:
            await broadcast_redis.close_shared_pools()
            await proxy.stop()
    assert fake.published == [("EventNotifier", "after")]


@pytest.mark.asyncio
async def test_cancelled_subscriber_closes_return_their_connections(
    short_timeouts, monkeypatch
):
    monkeypatch.setattr(broadcast_redis, "POOL_MAX_CONNECTIONS", 2)
    async with FakeRedis() as fake:
        for _ in range(3):
            backend = RedisBroadcastBackend(fake.url())
            await backend.connect()
            await backend.subscribe("EventNotifier")
            closing = asyncio.ensure_future(backend.disconnect())
            await asyncio.sleep(0)
            closing.cancel()
            with suppress(asyncio.CancelledError):
                await closing
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            await broadcast.publish("EventNotifier", "after")
    assert fake.published == [("EventNotifier", "after")]


def test_a_url_parameter_that_clashes_with_the_pool_is_refused_at_startup():
    with pytest.raises(ValueError, match="timeout"):
        check_redis_url("redis://localhost:6379?timeout=5")


@pytest.mark.asyncio
async def test_a_max_connections_url_parameter_does_not_change_the_pool():
    url_options = "?max_connections=50"

    async def publish(number: int) -> None:
        async with EndOnLossBroadcast(fake.url() + url_options) as broadcast:
            await broadcast.publish("EventNotifier", str(number))

    async with FakeRedis() as fake:
        check_redis_url(fake.url() + url_options)
        await asyncio.gather(*(publish(number) for number in range(30)))
    assert len(fake.published) == 30
    assert fake.accepts <= broadcast_redis.POOL_MAX_CONNECTIONS


@pytest.mark.asyncio
async def test_a_pooled_connection_is_replaced_once_it_reaches_its_age(monkeypatch):
    """After a failover that leaves old connections open, a pooled connection
    could keep publishing to the demoted node; replacing it by age makes the
    next publish connect (and resolve the host) again."""
    monkeypatch.setattr(broadcast_redis, "POOL_CONNECTION_MAX_AGE_SECONDS", 0.3)
    async with FakeRedis() as fake:
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            await broadcast.publish("EventNotifier", "first")
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            await broadcast.publish("EventNotifier", "young")
        assert fake.accepts == 1
        await asyncio.sleep(0.4)
        async with EndOnLossBroadcast(fake.url()) as broadcast:
            await broadcast.publish("EventNotifier", "old")
        await _wait_for(lambda: fake.closed_sessions)
    assert [message for _, message in fake.published] == ["first", "young", "old"]
    assert fake.accepts == 2


@pytest.mark.asyncio
async def test_the_subscriber_connection_is_not_replaced_by_age(monkeypatch):
    monkeypatch.setattr(broadcast_redis, "POOL_CONNECTION_MAX_AGE_SECONDS", 0.2)
    resyncs = []
    notifier = _Notifier()
    async with FakeRedis() as fake:
        broadcaster = _reconnecting(fake.url(), notifier=notifier)
        broadcaster.set_reconnect_callback(lambda: _record(resyncs))
        async with broadcaster.get_listening_context():
            await _wait_for(lambda: fake.subscribes == 1 and fake.sessions)
            for number in range(4):
                await asyncio.sleep(0.15)
                async with EndOnLossBroadcast(fake.url()) as broadcast:
                    await broadcast.publish("EventNotifier", _notification(number))
            await _wait_for(lambda: len(notifier.notified) == 4)
    assert fake.subscribes == 1
    assert resyncs == []
