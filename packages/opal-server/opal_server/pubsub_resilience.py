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
from fastapi_websocket_pubsub import EventBroadcaster, PubSubEndpoint
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
    after ``reconnect_max_retries`` consecutive failures (give-up), in which case it
    fires the registered give-up hook so OPAL graceful-restarts the worker.
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
        # (A) single-flight resync hook. Gap detection itself is reader-task-local
        # (see __read_notifications__), not an instance flag.
        self._recovery_task: Optional[asyncio.Task] = None
        # Set when a gap arrives while a recovery is already in flight (single-flight),
        # so the in-flight recovery loops once more rather than dropping that gap.
        self._recovery_rerun_requested = False
        self._on_reconnect: Optional[ReconnectCallback] = None
        # Fired once if the reader gives up (exhausts reconnect retries) and returns,
        # so OPAL can graceful-restart the worker even with statistics disabled.
        self._on_give_up: Optional[ReconnectCallback] = None
        # Live backbone-subscription state; see is_backbone_connected() / is_in_backbone_gap().
        # Instance attrs (not task-local): FreezablePubSubEndpoint reads them from outside
        # the reader task.
        self._backbone_connected = False
        # Whether this broadcaster ever held a backbone subscription — distinguishes a real
        # GAP (had a session, lost it) from "never connected yet" (boot, or backbone down
        # from the start), where freezing would be wrong: no resync fires on a FIRST
        # connect, so anything frozen before it would be lost, not deferred.
        self._had_backbone_connection = False

    def set_reconnect_callback(self, callback: Optional[ReconnectCallback]):
        """Register an ``async () -> None`` callback fired once after each gap
        (a reconnect that follows a previously-established connection)."""
        self._on_reconnect = callback

    def set_give_up_callback(self, callback: Optional[ReconnectCallback]):
        """Register an ``async () -> None`` callback fired once if the reader
        gives up after exhausting ``reconnect_max_retries``.

        Fires only when the reader task completes by *returning* (give-
        up), never on cancellation (clean shutdown), so OPAL can wire it
        to a graceful worker restart without normal shutdown re-
        triggering it.
        """
        self._on_give_up = callback

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
        # Scope gap detection to THIS reader task: a stale True from a previous task
        # (reader cancelled when the last listener left, then restarted later) would make
        # is_in_backbone_gap() freeze publishes before the new task's FIRST subscribe —
        # but a first connect fires no resync, so those publishes would be lost, not
        # deferred. Same task-scoping rationale as ``had_prior_connection`` in
        # ``__read_notifications__``.
        self._had_backbone_connection = False
        self._subscription_task = asyncio.create_task(self.__read_notifications__())
        return self._subscription_task

    def is_reader_healthy(self) -> bool:
        """Report whether the reconnecting reader can still serve connected
        clients.

        Used by the server ``/healthcheck`` so a k8s readiness/liveness probe can
        route away from (or restart) a worker whose reader is wedged while clients
        depend on it — defense in depth on top of the reconnect loop itself.

        Health is judged against the listener count, not the backbone connection:

        * No listeners (``_listen_count <= 0``): healthy. The reader is started lazily
          when the count goes 0->1 and reset to ``None`` when it returns to 0, so its
          absence here is expected idleness, not a fault — nothing depends on it.
        * Listeners present: healthy only while the reader task is a live, *pending*
          task. A pending task INCLUDES the case where it is mid-reconnect through a
          backbone outage: ``ReconnectingBroadcaster`` deliberately keeps the reader
          pending across a drop, so a transient reconnect must NOT read as unhealthy
          (otherwise the probe would flap the pod during every normal backbone blip).
          It reads unhealthy only in the two wedged states — the task is ``None``
          (never started / leaked listen-count) or ``done`` (crashed, or gave up after
          ``reconnect_max_retries``) — which is exactly when clients are stuck.

        This is a cheap, non-blocking attribute read (no await, no lock); any rare race
        against a reconnect is absorbed by the probe's ``failureThreshold``.

        Returns:
            bool: True if idle or the reader is live and pending; False if listeners
            depend on a missing or completed reader task.
        """
        if self._listen_count <= 0:
            return True
        return (
            self._subscription_task is not None and not self._subscription_task.done()
        )

    def is_backbone_connected(self) -> bool:
        """Whether the reader currently holds a live backbone subscription.

        True only while actively subscribed — i.e. a publish right now would actually
        reach peer workers. Flips False the instant the subscription drops and back to
        True only once re-subscribed.

        This is intentionally NOT ``is_reader_healthy()``: that one stays True across a
        transient reconnect (so the k8s probe does not flap the pod), which is exactly the
        wrong signal for gating delivery.
        """
        return self._backbone_connected

    def is_in_backbone_gap(self) -> bool:
        """Whether the broadcaster is mid-GAP: it *had* a live backbone subscription,
        lost it, and the reader is still trying to get it back.

        This — not mere "not connected" — is the publish-freeze condition used by
        ``FreezablePubSubEndpoint``, because only a real gap has the recovery path the
        freeze relies on (the ``on_reconnect`` resync fires exclusively for reconnects
        that follow an established session). The two excluded states must NOT freeze:

        * **Reader not running** (no listeners yet / worker idle / last client left and
          the upstream cancelled the reader): the backbone may be perfectly healthy —
          freezing here would silently drop publishes fleet-wide with nothing to ever
          reconcile them. Delegating preserves the pre-freeze behavior (share-context
          broadcast + local delivery).
        * **Never connected in this reader's lifetime** (boot, or backbone already down
          at startup): a FIRST successful connect fires no gap recovery, so a publish
          frozen in this window would be lost, not deferred. Pre-freeze behavior
          (deliver locally, buffer outbound for replay) is strictly better here.
        """
        return (
            self._subscription_task is not None
            and not self._subscription_task.done()
            and self._had_backbone_connection
            and not self._backbone_connected
        )

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
                # buffering disabled — the gap resync is the only recovery path.
                logger.warning(
                    f"Broadcast to backbone failed ({error!r}); replay buffer disabled"
                )
                return
            # At capacity this append drops the oldest entry (bounded deque); the resync
            # on reconnect still reconciles clients, so the drop only widens the window.
            overflow = len(self._outbound_buffer) >= self._replay_buffer_size
            self._outbound_buffer.append((topic, data))
            logger.warning(
                f"Broadcast to backbone failed ({error!r}); buffered for replay "
                f"({len(self._outbound_buffer)}/{self._replay_buffer_size}"
                f"{', OVERFLOW — oldest dropped' if overflow else ''})"
            )

    async def __read_notifications__(self):
        """Read incoming broadcasts, reconnecting on backbone disconnect.

        ``had_prior_connection`` is deliberately a task-local, not an instance
        attribute: gap recovery must fire only for a reconnect *within this
        reader task's own loop* (a real backbone gap). When the last client
        disconnects, the upstream cancels this task and clears
        ``_subscription_task``; the next client starts a *fresh* reader task,
        which must start clean — an instance flag would carry a stale ``True``
        into that fresh task and schedule a spurious full recovery (flush +
        client-recycling resync) on its very first connect, a churn loop that
        also hits stats-off deployments.
        """
        attempt = 0
        had_prior_connection = False
        while True:
            try:
                channel = await self._ensure_connected()
                logger.info(
                    f"Broadcaster listener connected to channel '{self._channel}'"
                )
                async with channel.subscribe(channel=self._channel) as subscriber:
                    # Subscribed: the backbone is reachable, so publishes will fan out to
                    # peers again — reopen the publish gate (see FreezablePubSubEndpoint).
                    self._backbone_connected = True
                    self._had_backbone_connection = True
                    # We are subscribed again; recover concurrently so we keep reading
                    # (and can receive peers' replays) during the settle window.
                    if had_prior_connection:
                        self._schedule_gap_recovery()
                    had_prior_connection = True
                    # A connect that ends without sustaining (no read) is a flap, not a
                    # healthy session, so only a sustained subscriber resets the attempt
                    # counter — otherwise a connect-OK/instant-close loop would never
                    # increment ``attempt`` and ``reconnect_max_retries`` could never trip.
                    sustained = False
                    async for event in subscriber:
                        if not sustained:
                            sustained = True
                            attempt = 0
                        await self._handle_broadcast_event(event)
                if sustained:
                    logger.warning(
                        "Broadcast subscriber ended (backbone connection closed); "
                        "reconnecting"
                    )
                else:
                    attempt += 1
                    logger.warning(
                        "Broadcast subscriber ended immediately without sustaining "
                        f"(attempt {attempt}); treating as a failed reconnect"
                    )
                    if self._gave_up(attempt):
                        await self._fire_give_up()
                        return
            except asyncio.CancelledError:
                logger.info("Broadcaster listener cancelled; stopping")
                await self._cancel_pending_tasks()
                raise
            except Exception as e:
                attempt += 1
                logger.error(f"Broadcaster listener error (attempt {attempt}): {e!r}")
                if self._gave_up(attempt):
                    await self._fire_give_up()
                    return
            finally:
                # Any exit from the read cycle (backbone closed, error, or cancel) means we
                # are no longer subscribed — close the publish gate until we re-subscribe, so
                # a write during the gap is not applied on this worker alone.
                self._backbone_connected = False
                await self._safe_disconnect_channel()
            await asyncio.sleep(self._backoff_seconds(attempt))

    def _gave_up(self, attempt: int) -> bool:
        """Return whether ``reconnect_max_retries`` is exhausted (0 = retry
        forever)."""
        if self._reconnect_max_retries and attempt >= self._reconnect_max_retries:
            logger.error(
                f"Broadcaster reconnect exhausted after {attempt} attempts; "
                "giving up so the worker can restart"
            )
            return True
        return False

    async def _cancel_pending_tasks(self):
        # Cancel AND join child notify/recovery tasks so they fully unwind (releasing any
        # pinned listening context) before the reader re-raises its own cancellation.
        # Exclude the current task defensively (the reader is not in _tasks, but be safe).
        current = asyncio.current_task()
        tasks = [task for task in self._tasks if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _schedule_gap_recovery(self):
        # Single-flight: a flap during a recovery must not spawn a second concurrent
        # recovery (concurrent flushes corrupt the buffer; double resync re-storms).
        # Instead, request a rerun so a gap that lands while a recovery is in flight —
        # including during the late ``_fire_reconnect`` phase, after the flush — is still
        # flushed/resynced by one more loop of the in-flight recovery rather than dropped.
        if self._recovery_task is not None and not self._recovery_task.done():
            logger.debug("Gap recovery already in progress; requesting a rerun")
            self._recovery_rerun_requested = True
            return
        self._recovery_rerun_requested = False
        self._recovery_task = asyncio.create_task(self._recover_after_gap())
        self._tasks.add(self._recovery_task)
        self._recovery_task.add_done_callback(self._tasks.discard)

    async def _recover_after_gap(self):
        """After reconnecting following a gap: let peers re-subscribe, replay the
        buffer (B), then fire the resync hook (A).

        The whole recovery runs inside a pinned listening context so the reader task
        cannot be cancelled mid-recovery — neither by the resync hook closing every
        client nor by an unrelated drop to zero listeners during the settle window.

        Loops once more whenever a gap arrives during an iteration (single-flight rerun):
        the rerun flag is cleared at the top of each iteration and re-checked after the
        full pin -> settle -> flush -> fire body, so a gap landing at any point during the
        body — clear happens first, check happens last — is captured and triggers exactly
        one more iteration (single-threaded asyncio, no lock needed).
        """
        try:
            while True:
                self._recovery_rerun_requested = False
                async with self.get_listening_context():
                    if self._resync_settle_seconds > 0:
                        await asyncio.sleep(self._resync_settle_seconds)
                    await self._flush_outbound_buffer()
                    await self._fire_reconnect()
                if not self._recovery_rerun_requested:
                    break
                logger.info(
                    "Gap arrived during recovery; rerunning flush + resync once"
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error during post-reconnect broadcast recovery")

    async def _flush_outbound_buffer(self):
        """Replay buffered broadcasts to the backbone (best-effort).

        The buffer is drained into a local snapshot under ``_buffer_lock`` and then
        published WITHOUT the lock, so a concurrent failed broadcast can still buffer
        (and a slow/hung publish can't wedge the buffer lock). Items that can no longer
        be serialized are dropped (so one poison payload can't wedge the buffer); a
        transport failure re-enqueues the unsent (older) tail ahead of any concurrent
        refill (newer) for the next recovery (see ``_requeue_unsent``).
        """
        async with self._buffer_lock:
            if not self._outbound_buffer:
                return
            pending = list(self._outbound_buffer)
            self._outbound_buffer.clear()
        logger.info(f"Replaying {len(pending)} buffered broadcast(s) after recovery")
        unsent = list(pending)
        try:
            async with self._broadcast_type(self._broadcast_url) as channel:
                while unsent:
                    topic, data = unsent[0]
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
                        unsent.pop(0)
                        continue
                    await channel.publish(self._channel, payload)
                    unsent.pop(0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to replay buffered broadcasts ({len(unsent)} left, will retry "
                f"on next recovery): {e!r}"
            )
            if unsent:
                await self._requeue_unsent(unsent)

    async def _requeue_unsent(self, unsent: list):
        """Re-enqueue the unsent (older) tail ahead of any concurrent refill
        (newer).

        The publish above ran WITHOUT the lock, so concurrent failed broadcasts may have
        refilled the buffer meanwhile. Rebuild under the lock as ``unsent + refill`` and
        rely on the bounded deque dropping from the FRONT (oldest) on overflow — a plain
        ``extendleft`` would instead evict the newest refill, inverting the drop-oldest
        policy on a deque that is already at ``maxlen``.
        """
        async with self._buffer_lock:
            refill = list(self._outbound_buffer)
            self._outbound_buffer.clear()
            self._outbound_buffer.extend(unsent)
            self._outbound_buffer.extend(refill)

    async def _fire_reconnect(self):
        if self._on_reconnect is None:
            return
        try:
            await self._on_reconnect()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Broadcaster on_reconnect callback failed")

    async def _fire_give_up(self):
        """Fire the give-up hook so OPAL can graceful-restart the worker.

        Called only from the give-up (returning) path of the reader
        loop, never on cancellation, so a clean shutdown does not re-
        trigger the restart. If no hook is wired, log loudly that this
        worker now depends on the liveness probe.
        """
        if self._on_give_up is None:
            logger.error(
                "Broadcaster gave up reconnecting and no give-up hook is wired; this "
                "worker now requires the liveness probe (/healthcheck) to be restarted"
            )
            return
        try:
            await self._on_give_up()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Broadcaster on_give_up callback failed")

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


class FreezablePubSubEndpoint(PubSubEndpoint):
    """A ``PubSubEndpoint`` that *freezes* client-facing publishes during a
    broadcaster backbone GAP, to keep a multi-worker fleet consistent through
    an outage.

    The problem: a server-side ``publish`` fans out two independent ways — local in-process
    delivery to *this* worker's own clients, and (via the broadcaster) to peer workers. Only
    the outbound path is buffered when the backbone is down; local delivery still fires. So a
    data/policy update that reaches one worker during a backbone gap is applied to that
    worker's clients but not the fleet — a transient split (some PDPs new, others old) that
    lasts the whole outage.

    With freeze enabled, while the ``ReconnectingBroadcaster`` reports a real gap
    (``is_in_backbone_gap()`` — an established backbone session was lost and is being
    re-acquired; see its docstring for why "never connected" and "reader not running" must
    NOT freeze), ``publish`` is skipped entirely: neither local clients nor the outbound
    buffer see it. The write still lands in the source of truth, and the reconnect *resync*
    makes every worker's clients refetch on recovery — the whole fleet moves together.
    Skipping the whole publish also means nothing is buffered for replay during the freeze,
    so recovery converges purely via the resync refetch.

    **Exempt topics** keep the pre-freeze behavior (local delivery + outbound replay buffer)
    even mid-gap: topics prefixed ``__`` (the statistics protocol and the broadcaster
    keepalive — dropping those corrupts server-to-server state that no resync rebuilds:
    ghost clients, workers that never stat-sync) and any topic in ``freeze_exempt_topics``
    (OPAL passes the git-webhook trigger topic: it targets the server-side policy watcher,
    not clients, and a dropped trigger means the repo pull it requests simply never happens
    — the resync would then refetch from a clone that was never advanced).

    Delegates straight to the base when: freeze is disabled; there is no broadcaster
    (single worker); or the broadcaster is the stock ``EventBroadcaster``.

    **Recovery scope** (what "reconciled by the resync" actually covers): data the clients
    re-fetch on reconnect, i.e. their configured data sources (``OPAL_DATA_CONFIG_SOURCES``
    or scope config) and the policy bundle. One-off updates outside that set — an inline
    ``data`` payload, or a fetch URL that is not part of the configured sources — are
    dropped by a freeze, not deferred. Accepted trade: consistency over freshness, and such
    updates are the legacy path.

    **Known limitations** (all degrade to the PRE-freeze behavior, never worse):
    * If the reader's subscription is alive but an individual outbound broadcast fails
      (separate per-publish channel), the gate does not engage — that publish is delivered
      locally and buffered for replay, the pre-existing split-until-replay behavior.
    * The gate reopens when the subscription is re-established, before the session proves
      "sustained" — during a rare connect-then-instant-close flap a publish can slip
      through (deliver locally + buffer). Gating on sustained instead would wrongly freeze
      quiet channels forever (a session only proves sustained on its first inbound event).
    * Client-originated RPC publishes (``RpcEventServerMethods.publish``) notify the local
      subscribers directly, bypassing this override.
    """

    def __init__(
        self,
        *args,
        freeze_on_disconnect: bool = True,
        freeze_exempt_topics=(),
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._freeze_on_disconnect = freeze_on_disconnect
        self._freeze_exempt_topics = frozenset(freeze_exempt_topics)
        # Publishes suppressed in the current freeze episode — first one logs at WARNING,
        # the rest at DEBUG (a long outage would otherwise emit an unbounded WARNING per
        # frozen stats keepalive), and the first delivered publish afterwards logs a
        # summary count.
        self._frozen_in_episode = 0

    def _is_exempt(self, topics) -> bool:
        if isinstance(topics, str):
            topics = [topics]
        return all(
            topic.startswith("__") or topic in self._freeze_exempt_topics
            for topic in topics
        )

    def _should_freeze(self, topics) -> bool:
        broadcaster = self.broadcaster
        return (
            self._freeze_on_disconnect
            and isinstance(broadcaster, ReconnectingBroadcaster)
            and broadcaster.is_in_backbone_gap()
            and not self._is_exempt(topics)
        )

    async def publish(self, topics, data=None):
        if self._should_freeze(topics):
            self._frozen_in_episode += 1
            log = logger.warning if self._frozen_in_episode == 1 else logger.debug
            log(
                "Broadcaster backbone gap; freezing publish to preserve fleet consistency "
                "(not delivered to clients; reconciled via resync on reconnect). "
                "topics={topics} (suppressed {count} so far this gap)",
                topics=topics,
                count=self._frozen_in_episode,
            )
            return
        if self._frozen_in_episode:
            count, self._frozen_in_episode = self._frozen_in_episode, 0
            logger.warning(
                "Backbone recovered; froze {count} publish(es) during the gap — clients "
                "reconcile via the reconnect resync",
                count=count,
            )
        return await super().publish(topics, data)

    # The library aliases ``notify = publish`` at class level (backward-compat canonical
    # name), which binds the BASE publish — re-bind it here or ``endpoint.notify(...)``
    # would silently bypass the freeze gate.
    notify = publish
