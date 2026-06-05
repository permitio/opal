"""Resilience wrappers around the ``fastapi_websocket_pubsub`` /
``fastapi_websocket_rpc`` pub/sub layer used by the OPAL server.

Two upstream issues let a *transient* broadcaster-backbone disconnect
(Postgres ``LISTEN/NOTIFY``, Redis, Kafka) escalate into a self-sustaining,
fleet-wide client connection-drop storm that only a worker restart clears:

1. ``EventBroadcaster``'s reader task runs to completion when the backbone
   connection drops and is never restarted while clients remain connected
   (``_subscription_task`` is reset only when the listener count reaches 0).
   Because OPAL runs with ``ignore_broadcaster_disconnected=False``, every
   client websocket waits on that shared reader task; once it is *done* every
   client is cancelled and dropped, indefinitely.
2. ``ConnectionManager.disconnect`` is not idempotent; the RPC endpoint can
   call it twice for the same socket, raising
   ``ValueError('list.remove(x): x not in list')``.

``ReconnectingBroadcaster`` keeps the reader task *pending* across transient
backbone losses by reconnecting with bounded exponential backoff.
``SafeConnectionManager`` makes ``disconnect`` idempotent. Both are stop-gaps
until the fixes land in the upstream libraries (see Phase 2 of the plan).
"""
import asyncio
import random

from fastapi import WebSocket
from fastapi_websocket_pubsub import EventBroadcaster
from fastapi_websocket_pubsub.event_broadcaster import BroadcastNotification
from fastapi_websocket_rpc.connection_manager import ConnectionManager
from opal_common.logger import logger


class SafeConnectionManager(ConnectionManager):
    """A ``ConnectionManager`` whose ``disconnect`` is idempotent.

    The upstream implementation calls ``self.active_connections.remove(websocket)``
    unconditionally, so a second disconnect for the same socket raises
    ``ValueError('list.remove(x): x not in list')``. That error escapes
    ``WebsocketRPCEndpoint.main_loop`` as an unretrieved task exception and, under a
    reconnect storm, is logged thousands of times. Guarding the removal turns a
    double disconnect into a no-op.
    """

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            logger.debug("Ignoring duplicate websocket disconnect")


class ReconnectingBroadcaster(EventBroadcaster):
    """An ``EventBroadcaster`` whose listener reconnects instead of dying.

    The base reader coroutine (``__read_notifications__``) returns when the backbone
    connection closes and is not restarted while clients stay connected, leaving
    ``get_reader_task()`` permanently *done* — which cancels every client websocket
    loop. This subclass wraps the connect/subscribe/read cycle in a reconnect loop
    with bounded exponential backoff, so the reader task stays *pending* across
    transient outages. The task only completes on clean shutdown (cancellation) or
    after ``reconnect_max_retries`` consecutive failures, in which case the existing
    ``ignore_broadcaster_disconnected=False`` path triggers a graceful worker restart.
    """

    def __init__(
        self,
        *args,
        reconnect_max_retries: int = 0,
        reconnect_backoff_min: float = 0.5,
        reconnect_backoff_max: float = 30.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._reconnect_max_retries = reconnect_max_retries
        self._reconnect_backoff_min = reconnect_backoff_min
        self._reconnect_backoff_max = reconnect_backoff_max

    async def start_reader_task(self):
        """Spawn the reconnecting reader task once.

        Unlike the base implementation we do not connect the channel
        here — the reader loop owns (re)connection, so a backbone that
        is already down at startup is retried rather than raised to the
        first connecting client.
        """
        if self._subscription_task is not None:
            logger.debug("No need for listen task, already started")
            return self._subscription_task
        logger.debug("Spawning reconnecting broadcast listen task")
        self._subscription_task = asyncio.create_task(self.__read_notifications__())
        return self._subscription_task

    async def __read_notifications__(self):
        """Read incoming broadcasts, reconnecting on backbone disconnect.

        ``__read_notifications__`` ends in a double underscore, so it is not a
        name-mangled private name and this override is what the inherited
        ``start_reader_task`` (and ours) dispatches to.
        """
        attempt = 0
        while True:
            try:
                channel = await self._ensure_connected()
                attempt = 0
                logger.info(
                    f"Broadcaster listener connected to channel '{self._channel}'"
                )
                async with channel.subscribe(channel=self._channel) as subscriber:
                    async for event in subscriber:
                        await self._handle_broadcast_event(event)
                logger.warning(
                    "Broadcast subscriber ended (backbone connection closed); reconnecting"
                )
            except asyncio.CancelledError:
                logger.info("Broadcaster listener cancelled; stopping")
                raise
            except Exception as e:
                attempt += 1
                logger.error(f"Broadcaster listener error (attempt {attempt}): {e!r}")
                if (
                    self._reconnect_max_retries
                    and attempt >= self._reconnect_max_retries
                ):
                    logger.error(
                        f"Broadcaster reconnect exhausted after {attempt} attempts; "
                        "giving up so the worker can restart"
                    )
                    break
            finally:
                await self._safe_disconnect_channel()
            await asyncio.sleep(self._backoff_seconds(attempt))

    async def _ensure_connected(self):
        if self.listening_broadcast_channel is None:
            self.listening_broadcast_channel = self._broadcast_type(self._broadcast_url)
            await self.listening_broadcast_channel.connect()
        return self.listening_broadcast_channel

    async def _handle_broadcast_event(self, event):
        """Forward one incoming broadcast to the internal notifier.

        Mirrors the base class' per-event handling; kept here so the
        reconnect loop above stays readable.
        """
        try:
            notification = BroadcastNotification.parse_raw(event.message)
            # Avoid re-publishing our own broadcasts
            if notification.notifier_id != self._id:
                logger.debug(
                    "Handling incoming broadcast event: {}".format(
                        {"topics": notification.topics, "src": notification.notifier_id}
                    )
                )
                task = asyncio.create_task(
                    self._notifier.notify(
                        notification.topics,
                        notification.data,
                        notifier_id=self._id,
                    )
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except Exception:
            logger.exception("Failed handling incoming broadcast")

    async def _safe_disconnect_channel(self):
        channel = self.listening_broadcast_channel
        self.listening_broadcast_channel = None
        if channel is not None:
            try:
                await channel.disconnect()
            except Exception:
                logger.debug("Error while disconnecting broadcast channel; ignoring")

    def _backoff_seconds(self, attempt: int) -> float:
        if attempt <= 0:
            base = self._reconnect_backoff_min
        else:
            base = self._reconnect_backoff_min * (2 ** (attempt - 1))
        base = min(base, self._reconnect_backoff_max)
        # Equal jitter, so a fleet of pods does not reconnect to the backbone in lockstep.
        return base / 2 + random.uniform(0, base / 2)
