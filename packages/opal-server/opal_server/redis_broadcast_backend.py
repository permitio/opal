"""A Redis broadcaster backend that reports a lost connection instead of hiding
it.

The stock Redis backend of the ``broadcaster`` package is built on
``asyncio-redis``, which reconnects on its own, inside the library, without
telling its caller. That leaves the OPAL server with two problems after the
Redis backbone restarts or the connection drops:

1. **With a Redis password the listener is never re-created.** On reconnect
   ``asyncio-redis`` re-sends ``AUTH`` while the connection is still flagged as
   being in pub/sub mode, its own guard rejects the command (``Cannot run
   command inside pubsub subscription``), and the ``SUBSCRIBE`` that would have
   followed is never sent (jonathanslenders/asyncio-redis#82). The server stays
   connected to Redis with no subscription: broadcasts from peer servers are
   silently lost until the worker is restarted.
2. **Without a password the listener comes back, but nobody knows there was a
   gap.** ``next_published()`` simply keeps waiting, so
   ``ReconnectingBroadcaster`` never sees a disconnect: no resync of the
   worker's clients, no publish freeze, and the broadcasts peers sent during
   the outage are lost with nothing to reconcile them.

``ResilientRedisBackend`` uses ``redis-py`` (already an OPAL server dependency)
with its retries turned off, and turns a dropped connection into the
``broadcaster`` "backend disconnected" signal: ``next_published()`` returns
``None``, exactly as the Postgres backend does when its connection terminates.
``ReconnectingBroadcaster`` then runs its normal reconnect loop: a fresh
connection, ``AUTH`` first, ``SUBSCRIBE`` after it, followed by the gap
recovery. Nothing reconnects behind its back.

The connection URL is read the same way the stock backend reads it (host, port
and password), so an existing ``OPAL_BROADCAST_URI`` keeps its meaning.
"""
import asyncio
import socket
from contextlib import suppress
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

from broadcaster import Broadcast
from broadcaster._backends.base import BroadcastBackend
from broadcaster._base import Event
from opal_common.logger import logger
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

REDIS_SCHEMES = ("redis", "rediss")

# Give up on a connection attempt that gets no answer, so an unreachable host
# costs one reconnect attempt instead of blocking the reader on the OS TCP
# timeout.
CONNECT_TIMEOUT_SECONDS = 10.0

# TCP keepalive on the Redis connections. A subscribed connection is idle by
# nature; if the peer goes silent without closing the socket (node death,
# network partition) no FIN/RST ever arrives and the listener would be deaf
# without any error. With these timings the kernel fails the connection about
# a minute after the peer went silent: 30 s idle, then 3 lost probes 10 s
# apart. Same defaults as the Postgres backend of permit-broadcaster.
KEEPALIVE_IDLE_SECONDS = 30
KEEPALIVE_INTERVAL_SECONDS = 10
KEEPALIVE_PROBE_COUNT = 3


def tcp_keepalive_options() -> Dict[int, int]:
    """The TCP keepalive socket options this platform supports.

    Linux names the idle timer ``TCP_KEEPIDLE``, macOS ``TCP_KEEPALIVE``. An
    option the platform does not define is left out, and the kernel default
    applies to it.
    """
    idle_option = getattr(socket, "TCP_KEEPIDLE", None) or getattr(
        socket, "TCP_KEEPALIVE", None
    )
    candidates = (
        (idle_option, KEEPALIVE_IDLE_SECONDS),
        (getattr(socket, "TCP_KEEPINTVL", None), KEEPALIVE_INTERVAL_SECONDS),
        (getattr(socket, "TCP_KEEPCNT", None), KEEPALIVE_PROBE_COUNT),
    )
    return {option: value for option, value in candidates if option is not None}


class ResilientRedisBackend(BroadcastBackend):
    """Redis pub/sub backend whose ``next_published()`` returns ``None`` when
    the connection to Redis is lost."""

    def __init__(self, url: str):
        parsed_url = urlparse(url)
        self._host = parsed_url.hostname or "localhost"
        self._port = parsed_url.port or 6379
        self._password = parsed_url.password or None
        self._client: Optional[Redis] = None
        self._pubsub: Any = None
        self._channels: Set[str] = set()
        self._reader_task: Optional[asyncio.Task] = None
        self._connection_lost = False
        self._queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> None:
        self._queue = asyncio.Queue()
        self._channels = set()
        self._connection_lost = False
        self._client = Redis(
            host=self._host,
            port=self._port,
            password=self._password,
            decode_responses=True,
            socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
            socket_keepalive=True,
            socket_keepalive_options=tcp_keepalive_options(),
            # No retries inside the client: a lost connection must surface here,
            # so the broadcaster's own reconnect loop handles it.
            retry=Retry(NoBackoff(), 0),
            retry_on_timeout=False,
        )
        try:
            # Connects and authenticates now, so a backbone that is down (or a
            # wrong password) fails this connect() instead of a later command.
            await self._client.ping()
        except BaseException:
            await self._close_client()
            raise

    async def disconnect(self) -> None:
        reader_task, self._reader_task = self._reader_task, None
        if reader_task is not None:
            reader_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await reader_task
        pubsub, self._pubsub = self._pubsub, None
        if pubsub is not None:
            with suppress(Exception):
                await pubsub.reset()
        self._channels = set()
        await self._close_client()

    async def subscribe(self, channel: str) -> None:
        if self._pubsub is None:
            self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(channel)
        self._channels.add(channel)
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._read_messages(self._pubsub))

    async def unsubscribe(self, channel: str) -> None:
        self._channels.discard(channel)
        # After a lost connection there is nothing to unsubscribe from, and
        # sending the command would make redis-py reconnect just to send it.
        if self._pubsub is None or self._connection_lost:
            return
        try:
            await self._pubsub.unsubscribe(channel)
        except Exception:
            # Best effort: the connection can drop at any moment.
            pass

    async def publish(self, channel: str, message: Any) -> None:
        await self._client.publish(channel, message)

    async def next_published(self) -> Optional[Event]:
        return await self._queue.get()

    async def _read_messages(self, pubsub: Any) -> None:
        """Move messages from Redis to the queue until the connection is lost.

        Queues ``None`` when the connection drops while a channel is still
        subscribed. Ends quietly after the last unsubscribe, and is cancelled by
        ``disconnect()``.
        """
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    await self._queue.put(
                        Event(channel=message["channel"], message=message["data"])
                    )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._connection_lost = True
            logger.warning(
                "Lost the Redis broadcast connection: {error!r}", error=error
            )
        if self._connection_lost and self._channels:
            await self._queue.put(None)

    async def _close_client(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        with suppress(Exception):
            # redis-py 5 renamed close() to aclose().
            close = getattr(client, "aclose", None) or client.close
            await close()
        with suppress(Exception):
            await client.connection_pool.disconnect()


class ResilientBroadcast(Broadcast):
    """``Broadcast`` that uses ``ResilientRedisBackend`` for Redis URLs.

    Every other backend (Postgres, Kafka, ...) is the stock one.
    """

    def __init__(self, url: str):
        super().__init__(url)
        if urlparse(url).scheme in REDIS_SCHEMES:
            self._backend = ResilientRedisBackend(url)
