"""OPAL's Redis broadcast backend, on redis-py's asyncio client.

The broadcaster library's own Redis backend reconnects and subscribes again by
itself, with no backoff, so OPAL's reconnecting reader never learns that a
connection was lost: it cannot back off, count the attempt toward
``BROADCAST_RECONNECT_MAX_RETRIES``, or resync clients after the gap. This
backend turns redis-py's own retries off and hands every lost connection to
its caller.

``EndOnLossBroadcast`` is the ``broadcast_type`` of OPAL's reconnecting
broadcaster: a lost subscriber connection ends the subscription, and the
reader reconnects through a new instance (every connection authenticates
when it connects, before it is used). ``ResubscribingBroadcast`` is for the
stock broadcaster (``BROADCAST_RECONNECT_ENABLED`` off), whose reader stops
for good when its subscription ends: there the backend reconnects and
subscribes again itself, backing off, and nothing resyncs clients after the
gap. Both use the library's own backends for every other scheme.

A ``rediss://`` URL connects over TLS, and the server's certificate and its
host name are verified.

The library opens a new ``Broadcast`` for every publish, so the backends of
one event loop share a pool of connections per URL: a publish reuses an idle
connection instead of opening (and authenticating, and with TLS handshaking)
a new one, and the reader's subscriber connection comes from the same pool.
A pooled connection is replaced once it is ``POOL_CONNECTION_MAX_AGE_SECONDS``
old, so that after a failover that leaves old connections open, publishes
reach the new primary.

Nothing the backend does waits forever, with fixed limits that the URL
cannot change: connecting (with AUTH), subscribing and publishing each time
out, every connection has TCP keepalive, and a subscriber that hears nothing
for ``PING_INTERVAL_SECONDS`` sends PING and counts no answer within
``PING_TIMEOUT_SECONDS`` as a lost connection.
"""

import asyncio
import random
import socket
import ssl
import weakref
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional
from urllib.parse import urlparse

from broadcaster import Broadcast, Event
from broadcaster._backends.base import BroadcastBackend
from opal_common.logger import logger
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.asyncio.connection import (
    BlockingConnectionPool,
    Connection,
    ConnectionPool,
    SSLConnection,
    parse_url,
)
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

REDIS_SCHEMES = ("redis", "rediss")

CONNECT_TIMEOUT_SECONDS = 10.0
PUBLISH_TIMEOUT_SECONDS = 10.0
PING_INTERVAL_SECONDS = 15.0
PING_TIMEOUT_SECONDS = 10.0
KEEPALIVE_IDLE_SECONDS = 30
KEEPALIVE_INTERVAL_SECONDS = 10
KEEPALIVE_PROBES = 3
POOL_MAX_CONNECTIONS = 10
POOL_CONNECTION_MAX_AGE_SECONDS = 60.0

RESUBSCRIBE_BACKOFF_MIN_SECONDS = 0.5
RESUBSCRIBE_BACKOFF_MAX_SECONDS = 30.0


def is_redis_url(url: str) -> bool:
    return urlparse(url).scheme in REDIS_SCHEMES


def connection_options(url: str) -> Dict[str, Any]:
    """The redis-py connection options for a broadcaster URL.

    The URL's own options (user, password, database and redis-py's query
    parameters) are kept. For ``rediss://``, redis-py verifies the
    certificate but not the host name unless asked, so the host name is
    verified unless the URL says ``ssl_check_hostname=false``. Whatever the
    URL says, redis-py's retries are off (OPAL makes every reconnect
    itself), and the timeouts, TCP keepalive, pool size and connection age
    are the backend's.
    """
    options: Dict[str, Any] = dict(parse_url(url))
    options.pop("max_connections", None)
    if options.get("connection_class") is SSLConnection:
        options.setdefault("ssl_check_hostname", True)
        options["connection_class"] = _AgedSSLConnection
    else:
        options["connection_class"] = _AgedConnection
    options.update(
        decode_responses=True,
        retry=None,
        retry_on_error=[],
        retry_on_timeout=False,
        socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
        socket_timeout=CONNECT_TIMEOUT_SECONDS,
        socket_keepalive=True,
        socket_keepalive_options=_keepalive_options(),
        health_check_interval=0,
    )
    return options


def _keepalive_options() -> Dict[int, int]:
    # macOS names the idle timer TCP_KEEPALIVE.
    idle = getattr(socket, "TCP_KEEPIDLE", None) or getattr(
        socket, "TCP_KEEPALIVE", None
    )
    options = {}
    for option, value in (
        (idle, KEEPALIVE_IDLE_SECONDS),
        (getattr(socket, "TCP_KEEPINTVL", None), KEEPALIVE_INTERVAL_SECONDS),
        (getattr(socket, "TCP_KEEPCNT", None), KEEPALIVE_PROBES),
    ):
        if option is not None:
            options[option] = value
    return options


@asynccontextmanager
async def _time_limit(seconds: float, failure: str) -> AsyncIterator[None]:
    """Run the block within ``seconds``.

    Raises:
        redis.exceptions.TimeoutError: the block, or a socket timeout inside
            it, ran out of time; the message is ``failure`` and the limit.
        redis.exceptions.ConnectionError: the block failed to connect. For a
            failed TLS handshake the message gives the TLS error, which
            redis-py's own message leaves out.
    """
    try:
        async with asyncio.timeout(seconds):
            yield
    except (TimeoutError, RedisTimeoutError):
        raise RedisTimeoutError(f"{failure} within {seconds:g} s") from None
    except RedisConnectionError as error:
        if isinstance(error.__context__, ssl.SSLError):
            raise RedisConnectionError(
                f"TLS with Redis failed: {error.__context__}"
            ) from error
        raise


_PoolsByUrl = Dict[str, ConnectionPool]
_pools: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _PoolsByUrl]" = (
    weakref.WeakKeyDictionary()
)


def _new_pool(options: Dict[str, Any]) -> ConnectionPool:
    """A pool of at most ``POOL_MAX_CONNECTIONS``; with all of them in use, a
    caller waits for one, within its own time limit."""
    return BlockingConnectionPool(
        max_connections=POOL_MAX_CONNECTIONS, timeout=None, **options
    )


def _shared_pool(url: str, options: Dict[str, Any]) -> ConnectionPool:
    """The connection pool of every backend for ``url`` on the running event
    loop."""
    pools = _pools.setdefault(asyncio.get_running_loop(), {})
    pool = pools.get(url)
    if pool is None:
        pool = _new_pool(options)
        pools[url] = pool
    return pool


class _AgedConnectionMixin:
    """A connection its pool replaces once it is
    ``POOL_CONNECTION_MAX_AGE_SECONDS`` old.

    TCP keepalive can hold a pooled connection open for good. After a
    failover that demotes the primary without closing its connections, a
    publish on such a connection still succeeds on the old node and reaches
    nobody subscribed on the new primary. The pool asks
    ``can_read_destructive`` whether a connection is ready each time it
    hands one out, and reconnects one that fails the check, which resolves
    the host again. The subscriber's connection is handed out once and kept,
    so it is never replaced this way.
    """

    _connected_at = 0.0

    async def on_connect(self) -> None:
        self._connected_at = asyncio.get_running_loop().time()
        await super().on_connect()

    async def can_read_destructive(self) -> bool:
        age = asyncio.get_running_loop().time() - self._connected_at
        if age > POOL_CONNECTION_MAX_AGE_SECONDS:
            raise RedisConnectionError(f"connection is {age:.0f} s old; replacing it")
        return await super().can_read_destructive()


class _AgedConnection(_AgedConnectionMixin, Connection):
    pass


class _AgedSSLConnection(_AgedConnectionMixin, SSLConnection):
    pass


async def close_shared_pools() -> None:
    """Close the connections the backends of the running event loop share."""
    for pool in _pools.pop(asyncio.get_running_loop(), {}).values():
        await pool.disconnect()


def check_redis_url(url: str) -> None:
    """Fail at startup on a Redis broadcaster URL redis-py cannot use.

    A ``rediss://`` URL that turns certificate or host name verification
    off is accepted, with a warning.

    Raises:
        ValueError: the URL names a query parameter redis-py does not know,
            or TLS settings that cannot make a TLS context (a CA file that
            does not exist, for example).
    """
    options = connection_options(url)
    try:
        connection = _new_pool(options).make_connection()
    except TypeError as error:
        raise ValueError(
            f"OPAL_BROADCAST_URI has a query parameter the Redis client does not "
            f"accept: {error}. Remove it from the URI."
        ) from None
    if isinstance(connection, SSLConnection):
        try:
            context = connection.ssl_context.get()
        except (OSError, ValueError) as error:
            raise ValueError(
                f"OPAL_BROADCAST_URI's TLS settings cannot be used: {error}"
            ) from None
        if context.verify_mode == ssl.CERT_NONE or not context.check_hostname:
            logger.warning(
                "OPAL_BROADCAST_URI turns TLS verification off (ssl_cert_reqs or "
                "ssl_check_hostname): the Redis broadcaster does not verify that it "
                "talks to the Redis the URI names"
            )


class RedisBroadcastBackend(BroadcastBackend):
    """A broadcaster backend on redis-py, for at most one subscribed channel.

    ``connect`` checks that a pooled connection works, opening (and
    authenticating, when the URL carries credentials) one when none is idle;
    ``subscribe`` subscribes on a pooled connection, which it keeps until
    ``disconnect``, and waits for Redis to confirm. When the subscriber
    connection is lost, ``next_published`` returns None from then on, or,
    with ``resubscribe``, reconnects and subscribes again itself, backing off
    from ``RESUBSCRIBE_BACKOFF_MIN_SECONDS`` to
    ``RESUBSCRIBE_BACKOFF_MAX_SECONDS``.
    It never raises: an exception would end the library's listener task
    without telling the subscribers, which then wait forever.
    """

    def __init__(self, url: str, resubscribe: bool = False) -> None:
        self._url = url
        self._options = connection_options(url)
        self._resubscribe = resubscribe
        self._pool: Optional[ConnectionPool] = None
        self._pubsub: Optional[PubSub] = None
        self._channel: Optional[str] = None
        self._subscribed = asyncio.Event()
        self._lost = False

    async def connect(self) -> None:
        pool = _shared_pool(self._url, self._options)
        async with _time_limit(CONNECT_TIMEOUT_SECONDS, "Redis did not connect"):
            connection = await pool.get_connection("PING")
            await pool.release(connection)
        self._pool = pool

    async def disconnect(self) -> None:
        """Close the subscriber connection; the pool's other connections stay
        open for the next publish."""
        pubsub, self._pubsub = self._pubsub, None
        if pubsub is not None:
            await _close(pubsub)

    async def subscribe(self, channel: str) -> None:
        if self._channel is not None:
            raise RuntimeError(
                f"The Redis broadcaster backend is already subscribed to "
                f"'{self._channel}'; it serves one channel"
            )
        self._channel = channel
        self._pubsub = await self._open_subscription()
        self._subscribed.set()

    async def unsubscribe(self, channel: str) -> None:
        """Do nothing: ``disconnect`` closes the subscriber connection, which
        ends the subscription, and the library drops events for channels
        nobody listens to."""

    async def publish(self, channel: str, message: Any) -> None:
        client = Redis(connection_pool=self._pool)
        async with _time_limit(
            PUBLISH_TIMEOUT_SECONDS, "Redis did not complete a PUBLISH"
        ):
            try:
                await client.publish(channel, message)
            except RedisConnectionError:
                # A pooled connection that Redis closed while it sat idle (a
                # Redis restart, Redis' idle timeout) fails its first command.
                # redis-py has closed it, so this try opens a fresh one.
                await client.publish(channel, message)

    async def next_published(self) -> Optional[Event]:
        await self._subscribed.wait()
        while not self._lost:
            try:
                message = await self._next_message()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "Lost the Redis broadcaster's subscriber connection: {error!r}",
                    error=error,
                )
                if not self._resubscribe:
                    self._lost = True
                    return None
                await self._subscribe_again()
                continue
            if message["type"] == "message":
                return Event(channel=message["channel"], message=message["data"])
        return None

    async def _next_message(self) -> Dict[str, Any]:
        """The next message on the subscriber connection, PINGing Redis after
        ``PING_INTERVAL_SECONDS`` of silence.

        Raises:
            redis.exceptions.TimeoutError: Redis did not answer the PING
                within ``PING_TIMEOUT_SECONDS``.
        """
        message = await self._pubsub.get_message(timeout=PING_INTERVAL_SECONDS)
        if message is not None:
            return message
        async with _time_limit(
            PING_TIMEOUT_SECONDS, "Sending PING to Redis did not end"
        ):
            await self._pubsub.ping()
        message = await self._pubsub.get_message(timeout=PING_TIMEOUT_SECONDS)
        if message is None:
            raise RedisTimeoutError(
                f"Redis did not answer PING within {PING_TIMEOUT_SECONDS:g} s"
            )
        return message

    async def _open_subscription(self) -> PubSub:
        """Subscribe to the channel on a pooled connection and read Redis'
        confirmation, so a subscription Redis refuses fails here, with its
        reason."""
        pubsub = PubSub(self._pool)
        try:
            async with _time_limit(
                CONNECT_TIMEOUT_SECONDS, "Redis did not confirm SUBSCRIBE"
            ):
                await pubsub.subscribe(self._channel)
                await pubsub.get_message(timeout=None)
        except BaseException:
            await _close(pubsub)
            raise
        return pubsub

    async def _subscribe_again(self) -> None:
        """Reconnect and subscribe again until it works, backing off."""
        pubsub, self._pubsub = self._pubsub, None
        await _close(pubsub)
        attempt = 0
        while True:
            await asyncio.sleep(_resubscribe_backoff_seconds(attempt))
            attempt += 1
            try:
                self._pubsub = await self._open_subscription()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "Redis broadcaster: subscribing again failed (attempt {attempt}): "
                    "{error!r}",
                    attempt=attempt,
                    error=error,
                )
                continue
            logger.warning(
                "Redis broadcaster: subscribed again after {attempt} attempt(s); "
                "updates published meanwhile were not received",
                attempt=attempt,
            )
            return


async def _close(pubsub: PubSub) -> None:
    """Close a subscriber connection that may already be broken, and return it
    to the shared pool.

    The socket is closed without waiting for the peer: a graceful close (a
    TLS close_notify) can wait on a Redis that went silent, or be cancelled,
    and ``reset`` only returns the connection to the pool once the close is
    done. A connection that never returns holds one of the pool's
    ``POOL_MAX_CONNECTIONS`` for good. A failure to close is logged and not
    raised: the connection is abandoned either way, and the caller is
    already handling the error that broke it.
    """
    try:
        if pubsub.connection is not None:
            await pubsub.connection.disconnect(nowait=True)
        await pubsub.reset()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.debug(
            "Redis broadcaster: closing a subscriber connection failed: {error!r}",
            error=error,
        )


def _resubscribe_backoff_seconds(attempt: int) -> float:
    # The exponent stops growing long after the cap is reached, so an outage of
    # any length never overflows the float.
    base = min(
        RESUBSCRIBE_BACKOFF_MIN_SECONDS * (2 ** min(attempt, 32)),
        RESUBSCRIBE_BACKOFF_MAX_SECONDS,
    )
    # Equal jitter, so the workers of a fleet do not reconnect in lockstep.
    return base / 2 + random.uniform(0, base / 2)


class EndOnLossBroadcast(Broadcast):
    """A ``broadcaster.Broadcast`` on OPAL's Redis backend for ``redis://`` and
    ``rediss://`` URLs, whose subscription ends when its connection is lost.

    Other schemes keep the library's backends.
    """

    _resubscribe = False

    def __init__(self, url: str) -> None:
        if not is_redis_url(url):
            super().__init__(url)
            return
        self._backend = RedisBroadcastBackend(url, resubscribe=self._resubscribe)
        self._subscribers: Dict[str, Any] = {}


class ResubscribingBroadcast(EndOnLossBroadcast):
    """Like ``EndOnLossBroadcast``, but a lost Redis connection is reopened and
    subscribed again by the backend, for a reader that does not reconnect by
    itself."""

    _resubscribe = True
