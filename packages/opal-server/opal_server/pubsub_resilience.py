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
backbone losses by reconnecting with bounded exponential backoff, and adds two
consistency mechanisms so a backbone gap does not silently desync instances:

* **(B) outbound replay buffer** — broadcasts that fail to reach the backbone
  while it is down are kept in a bounded FIFO and replayed once it reconnects,
  so peers that re-subscribe in time catch up without a refetch. This narrows
  the staleness window; it is *not* a delivery guarantee (the backbone keeps no
  replay of its own and a slow peer may not have re-subscribed at flush time).
* **(A) resync on recovery** — the *guarantee*. After **any** gap the broadcaster
  fires the registered ``on_reconnect`` callback. OPAL uses it to make this
  worker's own clients re-run their full (scope-aware) policy + data
  reconciliation. Every worker experiences the same gap, so every worker
  reconciles its own clients (a worker's clients may have missed *incoming* peer
  updates during the gap — independent of what this worker published), and the
  fleet converges to current truth.

``SafeConnectionManager`` makes ``disconnect`` idempotent and can close a
worker's client connections (staggered) to drive the resync. All of this is a
stop-gap until the fixes land in the upstream libraries (see Phase 2 of the plan).
"""
import asyncio
import random
from collections import deque
from typing import Awaitable, Callable, Optional

from fastapi import WebSocket
from fastapi_websocket_pubsub import EventBroadcaster
from fastapi_websocket_pubsub.event_broadcaster import BroadcastNotification
from fastapi_websocket_pubsub.event_notifier import Subscription
from fastapi_websocket_pubsub.util import pydantic_serialize
from fastapi_websocket_rpc.connection_manager import ConnectionManager
from opal_common.logger import logger

ReconnectCallback = Callable[[], Awaitable[None]]


class SafeConnectionManager(ConnectionManager):
    """A ``ConnectionManager`` whose ``disconnect`` is idempotent, able to drop
    its connections on demand.

    The upstream ``disconnect`` calls ``self.active_connections.remove(websocket)``
    unconditionally, so a second disconnect for the same socket raises
    ``ValueError('list.remove(x): x not in list')`` — which escapes
    ``WebsocketRPCEndpoint.main_loop`` as an unretrieved task exception and, under a
    reconnect storm, is logged thousands of times. Guarding the removal turns a
    double disconnect into a no-op. ``close_all_staggered`` additionally lets the
    server intentionally recycle its client connections (e.g. to force a post-outage
    resync) without a thundering herd.
    """

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            logger.debug("Ignoring duplicate websocket disconnect")

    async def close_all_staggered(
        self, min_interval: float = 0.0, max_interval: float = 0.2
    ) -> int:
        """Close every currently-tracked client websocket, spaced out with
        jitter.

        Clients reconnect on their own and re-run their on-connect reconciliation,
        so this is how a worker forces its clients back to a consistent state after
        a broadcaster gap. Close code 1012 ("Service Restart") signals a reconnect.

        Note: the broadcaster's reader task is tied to the per-client listening
        context, so the caller MUST pin a listening context around this call (see
        ``opal_server.pubsub``) — otherwise closing the last client cancels the
        reader we just worked to keep alive.
        """
        connections = list(self.active_connections)
        if not connections:
            return 0
        logger.info(
            f"Resync: closing {len(connections)} client connection(s) to trigger "
            "client-side reconciliation"
        )
        closed = 0
        for index, websocket in enumerate(connections):
            try:
                await websocket.close(code=1012)
                closed += 1
            except Exception as e:
                logger.warning(f"Error closing a client websocket during resync: {e!r}")
            # Jitter between closes (but not after the last one).
            if max_interval > 0 and index < len(connections) - 1:
                await asyncio.sleep(random.uniform(min_interval, max_interval))
        return closed


class ReconnectingBroadcaster(EventBroadcaster):
    """An ``EventBroadcaster`` whose listener reconnects instead of dying,
    buffers failed outbound broadcasts, and fires a resync hook after a gap.

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
        replay_buffer_size: int = 10000,
        resync_settle_seconds: float = 2.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._reconnect_max_retries = reconnect_max_retries
        self._reconnect_backoff_min = reconnect_backoff_min
        self._reconnect_backoff_max = reconnect_backoff_max
        self._replay_buffer_size = replay_buffer_size
        self._resync_settle_seconds = resync_settle_seconds
        # (B) bounded outbound replay buffer; deque(maxlen) drops the oldest on overflow.
        self._outbound_buffer: deque = deque(
            maxlen=replay_buffer_size if replay_buffer_size > 0 else None
        )
        # Single lock serialises buffer mutation, the overflow flag, and the flush,
        # so a concurrent broadcast cannot race the flush's drain/flag-reset.
        self._buffer_lock = asyncio.Lock()
        self._buffer_overflowed = False
        # (A) gap detection + single-flight resync hook.
        self._had_prior_connection = False
        self._recovery_task: Optional[asyncio.Task] = None
        self._on_reconnect: Optional[ReconnectCallback] = None

    def set_reconnect_callback(self, callback: Optional[ReconnectCallback]):
        """Register an ``async () -> None`` callback fired once after each gap
        (a reconnect that follows a previously-established connection)."""
        self._on_reconnect = callback

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

    async def __broadcast_notifications__(self, subscription: Subscription, data):
        """Share a local notification with the backbone; buffer it on failure.

        ``__broadcast_notifications__`` ends in a double underscore (not name-mangled),
        so this override is what ``_subscribe_to_all_topics`` dispatches to. The local
        delivery to this worker's own clients is independent of this publish (it runs
        as a sibling notifier callback), so a failure here means only "peers may miss
        this" — we keep it for replay rather than dropping it.
        """
        try:
            await super().__broadcast_notifications__(subscription, data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._buffer_outbound(subscription.topic, data, e)

    async def _buffer_outbound(self, topic, data, error: Exception):
        async with self._buffer_lock:
            if self._replay_buffer_size <= 0:
                # buffering disabled — nothing to replay; the gap resync is the only
                # recovery path. Nothing to record here.
                logger.warning(
                    f"Broadcast to backbone failed ({error!r}); replay buffer disabled"
                )
                return
            if len(self._outbound_buffer) >= self._replay_buffer_size:
                # at capacity: this append drops the oldest entry, unrecoverable.
                self._buffer_overflowed = True
            self._outbound_buffer.append((topic, data))
            logger.warning(
                f"Broadcast to backbone failed ({error!r}); buffered for replay "
                f"({len(self._outbound_buffer)}/{self._replay_buffer_size}"
                f"{', OVERFLOW' if self._buffer_overflowed else ''})"
            )

    async def __read_notifications__(self):
        """Read incoming broadcasts, reconnecting on backbone disconnect."""
        attempt = 0
        while True:
            try:
                channel = await self._ensure_connected()
                attempt = 0
                logger.info(
                    f"Broadcaster listener connected to channel '{self._channel}'"
                )
                async with channel.subscribe(channel=self._channel) as subscriber:
                    # We are subscribed again; recover concurrently so we keep reading
                    # (and can receive peers' replays) during the settle window.
                    if self._had_prior_connection:
                        self._schedule_gap_recovery()
                    self._had_prior_connection = True
                    async for event in subscriber:
                        await self._handle_broadcast_event(event)
                logger.warning(
                    "Broadcast subscriber ended (backbone connection closed); reconnecting"
                )
            except asyncio.CancelledError:
                logger.info("Broadcaster listener cancelled; stopping")
                self._cancel_pending_tasks()
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

    def _cancel_pending_tasks(self):
        for task in list(self._tasks):
            task.cancel()

    def _schedule_gap_recovery(self):
        # Single-flight: a flap during the settle window must not spawn a second
        # recovery (concurrent flushes corrupt the buffer; double resync re-storms).
        if self._recovery_task is not None and not self._recovery_task.done():
            logger.debug("Gap recovery already in progress; not scheduling another")
            return
        self._recovery_task = asyncio.create_task(self._recover_after_gap())
        self._tasks.add(self._recovery_task)
        self._recovery_task.add_done_callback(self._tasks.discard)

    async def _recover_after_gap(self):
        """After reconnecting following a gap: let peers re-subscribe, replay the
        buffer (B), then fire the resync hook (A)."""
        try:
            if self._resync_settle_seconds > 0:
                await asyncio.sleep(self._resync_settle_seconds)
            await self._flush_outbound_buffer()
            await self._fire_reconnect()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error during post-reconnect broadcast recovery")

    async def _flush_outbound_buffer(self):
        """Replay buffered broadcasts to the backbone (best-effort).

        Held under ``_buffer_lock`` so a concurrent failed broadcast cannot mutate
        the buffer mid-drain. Items that can no longer be serialized are dropped (so
        one poison payload can't wedge the buffer); a transport failure stops the
        drain and leaves the rest for the next recovery.
        """
        async with self._buffer_lock:
            self._buffer_overflowed = False
            if not self._outbound_buffer:
                return
            count = len(self._outbound_buffer)
            logger.info(f"Replaying {count} buffered broadcast(s) after recovery")
            try:
                async with self._broadcast_type(self._broadcast_url) as channel:
                    while self._outbound_buffer:
                        topic, data = self._outbound_buffer[0]
                        try:
                            payload = pydantic_serialize(
                                BroadcastNotification(
                                    notifier_id=self._id, topics=[topic], data=data
                                )
                            )
                        except Exception as e:
                            logger.error(
                                f"Dropping un-serializable buffered broadcast on "
                                f"topic '{topic}': {e!r}"
                            )
                            self._outbound_buffer.popleft()
                            continue
                        await channel.publish(self._channel, payload)
                        self._outbound_buffer.popleft()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    f"Failed to replay buffered broadcasts ({len(self._outbound_buffer)} "
                    f"left, will retry on next recovery): {e!r}"
                )

    async def _fire_reconnect(self):
        if self._on_reconnect is None:
            return
        try:
            await self._on_reconnect()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Broadcaster on_reconnect callback failed")

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
