"""Multi-instance consistency tests for the resilient broadcaster.

These wire two independent ``ReconnectingBroadcaster`` instances (modelling two
OPAL server workers/pods) to a single shared in-memory backbone with NOTIFY-like
semantics (only currently-subscribed peers receive a publish) and fault injection.
They assert the property that matters operationally: after a backbone outage during
which an update is published, **all instances converge to the same state** — via the
replay buffer (B) when possible, and via the resync hook (A) when delivery could not
be guaranteed.
"""
import asyncio

import pytest
from fastapi_websocket_pubsub.event_notifier import ALL_TOPICS
from fastapi_websocket_pubsub.websocket_rpc_event_notifier import (
    WebSocketRpcEventNotifier,
)
from opal_server.pubsub_resilience import ReconnectingBroadcaster

CHANNEL = "EventNotifier"
_CLOSED = object()


class _Event:
    def __init__(self, message):
        self.message = message


class InMemoryBackbone:
    """A tiny stand-in for the broadcaster.Broadcast backbone, shared by all
    channel instances.

    Like Postgres LISTEN/NOTIFY: a publish only reaches peers that are
    subscribed at that moment; nothing is queued for absent peers.
    """

    def __init__(self):
        self.faulted = False
        self._subscribers = {}  # channel -> set[asyncio.Queue]

    def factory(self, _url):
        return _Channel(self)

    def subscriber_count(self, channel=CHANNEL):
        return len(self._subscribers.get(channel, ()))

    def fault(self):
        self.faulted = True
        for queues in self._subscribers.values():
            for queue in list(queues):
                queue.put_nowait(_CLOSED)

    def recover(self):
        self.faulted = False

    def _subscribe(self, channel, queue):
        self._subscribers.setdefault(channel, set()).add(queue)

    def _unsubscribe(self, channel, queue):
        self._subscribers.get(channel, set()).discard(queue)

    def _deliver(self, channel, message):
        for queue in list(self._subscribers.get(channel, ())):
            queue.put_nowait(_Event(message))


class _Channel:
    def __init__(self, bus):
        self._bus = bus

    async def connect(self):
        if self._bus.faulted:
            raise ConnectionError("backbone down")

    async def disconnect(self):
        pass

    async def __aenter__(self):
        if self._bus.faulted:
            raise ConnectionError("backbone down")
        return self

    async def __aexit__(self, *exc):
        return False

    async def publish(self, channel, message):
        if self._bus.faulted:
            raise ConnectionError("backbone down")
        self._bus._deliver(channel, message)

    def subscribe(self, channel):
        return _Subscription(self._bus, channel)


class _Subscription:
    def __init__(self, bus, channel):
        self._bus = bus
        self._channel = channel
        self._queue = asyncio.Queue()

    async def __aenter__(self):
        self._bus._subscribe(self._channel, self._queue)
        return _Subscriber(self._queue)

    async def __aexit__(self, *exc):
        self._bus._unsubscribe(self._channel, self._queue)
        return False


class _Subscriber:
    def __init__(self, queue):
        self._queue = queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item


class Instance:
    """One server worker: its own notifier + reconnecting broadcaster + a recorder
    standing in for 'the state this worker's clients would have received'."""

    def __init__(self, bus, name, **broadcaster_kwargs):
        self.name = name
        self.notifier = WebSocketRpcEventNotifier()
        self.broadcaster = ReconnectingBroadcaster(
            "memory://",
            notifier=self.notifier,
            channel=CHANNEL,
            broadcast_type=bus.factory,
            reconnect_backoff_min=0.01,
            reconnect_backoff_max=0.02,
            **broadcaster_kwargs,
        )
        self.store = []
        self._reader = None
        self._listen_ctx = None

    async def start(self):
        async def record(subscription, data):
            self.store.append((subscription.topic, data))

        await self.notifier.subscribe(f"{self.name}-store", ALL_TOPICS, record)
        # Share this worker's local notifications with the backbone, and listen.
        await self.broadcaster._subscribe_to_all_topics()
        # Hold a listening context like a connected client would, so the reader is tied
        # to a non-zero listener count (as in production) and the recovery pin cannot
        # cancel it when that pin releases.
        self._listen_ctx = self.broadcaster.get_listening_context()
        await self._listen_ctx.__aenter__()
        self._reader = self.broadcaster.get_reader_task()

    async def publish(self, topic, data):
        await self.notifier.notify([topic], data, notifier_id=f"{self.name}-publisher")

    async def stop(self):
        if self._listen_ctx is not None:
            try:
                await self._listen_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._listen_ctx = None
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except (asyncio.CancelledError, Exception):
                pass


async def _wait_for(predicate, timeout=5.0):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met within timeout")


@pytest.mark.asyncio
async def test_instances_converge_after_backbone_outage():
    """An update published while the backbone is DOWN must still reach the
    other instance once the backbone recovers (replay buffer path)."""
    bus = InMemoryBackbone()
    a = Instance(bus, "A", resync_settle_seconds=0.05, replay_buffer_size=100)
    b = Instance(bus, "B", resync_settle_seconds=0.05, replay_buffer_size=100)
    await a.start()
    await b.start()
    try:
        await _wait_for(lambda: bus.subscriber_count() == 2)

        # Baseline: while connected, an update on A reaches B.
        await a.publish("policy_data", {"u": 1})
        await _wait_for(lambda: ("policy_data", {"u": 1}) in b.store)

        # Backbone drops; readers lose their subscriptions.
        bus.fault()
        await _wait_for(lambda: bus.subscriber_count() == 0)

        # Update during the outage: A's local store sees it, B does not (yet).
        await a.publish("policy_data", {"u": 2})
        await _wait_for(lambda: ("policy_data", {"u": 2}) in a.store)
        await asyncio.sleep(0.1)
        assert ("policy_data", {"u": 2}) not in b.store  # inconsistent *during* outage

        # Backbone recovers: A replays the buffered update; B converges.
        bus.recover()
        await _wait_for(lambda: ("policy_data", {"u": 2}) in b.store)

        # CONSISTENCY: both instances now hold the same updates.
        for store in (a.store, b.store):
            assert ("policy_data", {"u": 1}) in store
            assert ("policy_data", {"u": 2}) in store
    finally:
        await a.stop()
        await b.stop()


@pytest.mark.asyncio
async def test_resync_callback_fires_after_a_gap():
    """The resync hook fires once after a backbone gap so the worker can force
    its own clients to reconcile (a worker may have missed incoming peer
    updates during the gap, regardless of what it published)."""
    bus = InMemoryBackbone()
    a = Instance(bus, "A", resync_settle_seconds=0, replay_buffer_size=100)
    calls = []

    async def on_reconnect():
        calls.append(1)

    a.broadcaster.set_reconnect_callback(on_reconnect)
    await a.start()
    try:
        await _wait_for(lambda: bus.subscriber_count() == 1)
        bus.fault()
        await _wait_for(lambda: bus.subscriber_count() == 0)
        bus.recover()
        await _wait_for(lambda: calls)
        assert len(calls) == 1
    finally:
        await a.stop()


@pytest.mark.asyncio
async def test_resync_is_single_flight_across_a_flap_during_settle():
    """A second disconnect during the settle window must not spawn a second
    concurrent recovery (which would corrupt the buffer / double-resync)."""
    bus = InMemoryBackbone()
    # Long settle so a second gap lands while the first recovery is still pending.
    a = Instance(bus, "A", resync_settle_seconds=0.3, replay_buffer_size=100)
    calls = []

    async def on_reconnect():
        calls.append(1)

    a.broadcaster.set_reconnect_callback(on_reconnect)
    await a.start()
    try:
        await _wait_for(lambda: bus.subscriber_count() == 1)
        # First gap.
        bus.fault()
        await _wait_for(lambda: bus.subscriber_count() == 0)
        bus.recover()
        await _wait_for(lambda: bus.subscriber_count() == 1)
        # Second gap while the first recovery is still inside its settle sleep.
        bus.fault()
        await _wait_for(lambda: bus.subscriber_count() == 0)
        bus.recover()
        await _wait_for(lambda: bus.subscriber_count() == 1)
        # Let recoveries settle.
        await asyncio.sleep(1.0)
        # Single-flight: the overlapping flap collapses into one recovery, not three.
        assert len(calls) <= 2
        assert a.broadcaster._recovery_task is not None
        assert a.broadcaster._recovery_task.done()
    finally:
        await a.stop()


@pytest.mark.asyncio
async def test_resync_callback_does_not_fire_on_first_connect():
    """The resync hook is for *recovery*, not boot — it must not fire on the
    initial connection."""
    bus = InMemoryBackbone()
    a = Instance(bus, "A", resync_settle_seconds=0, replay_buffer_size=100)
    calls = []

    async def on_reconnect():
        calls.append(1)

    a.broadcaster.set_reconnect_callback(on_reconnect)
    await a.start()
    try:
        await _wait_for(lambda: bus.subscriber_count() == 1)
        await asyncio.sleep(0.2)
        assert calls == []
    finally:
        await a.stop()
