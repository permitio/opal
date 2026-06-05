"""Unit tests for ReconnectingBroadcaster.

The tests drive the broadcaster against an in-memory, fault-injectable backbone so
they are deterministic and require no real Postgres/Redis. The key invariant under
test is that a transient backbone disconnect must NOT complete the reader task (which
is what cancels every client websocket in production). The final test is a negative
control: the stock EventBroadcaster reader DOES complete on the same disconnect,
proving these tests actually catch the regression.
"""
import asyncio

import pytest
from fastapi_websocket_pubsub import EventBroadcaster
from fastapi_websocket_pubsub.event_broadcaster import BroadcastNotification
from opal_server.pubsub_resilience import ReconnectingBroadcaster

_END = object()


class _Event:
    def __init__(self, message):
        self.message = message


class FakeNotifier:
    def __init__(self):
        self.notified = []

    async def notify(self, topics, data, notifier_id=None):
        self.notified.append((list(topics), data, notifier_id))


class FakeBus:
    """A controllable in-memory broadcast backbone for a single channel."""

    def __init__(self, fail_connect=False):
        self.fail_connect = fail_connect
        self.connects = 0
        self.subscribes = 0
        self.disconnects = 0
        self.queue = asyncio.Queue()

    def channel_factory(self, _url):
        return _FakeChannel(self)

    async def drop(self):
        """Simulate the backbone closing the read connection."""
        await self.queue.put(_END)

    async def push(self, topics, data, notifier_id):
        note = BroadcastNotification(notifier_id=notifier_id, topics=topics, data=data)
        await self.queue.put(_Event(note.json()))


class _FakeChannel:
    def __init__(self, bus):
        self._bus = bus

    async def connect(self):
        self._bus.connects += 1
        if self._bus.fail_connect:
            raise ConnectionError("backbone refused connection")

    async def disconnect(self):
        self._bus.disconnects += 1

    def subscribe(self, channel):
        return _FakeSubscription(self._bus)


class _FakeSubscription:
    def __init__(self, bus):
        self._bus = bus

    async def __aenter__(self):
        self._bus.subscribes += 1
        return _FakeSubscriber(self._bus)

    async def __aexit__(self, *exc):
        return False


class _FakeSubscriber:
    def __init__(self, bus):
        self._bus = bus

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._bus.queue.get()
        if item is _END:
            raise StopAsyncIteration
        return item


async def _wait_for(predicate, timeout=2.0):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met within timeout")


@pytest.mark.asyncio
async def test_reader_reconnects_and_stays_pending():
    bus = FakeBus()
    notifier = FakeNotifier()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=notifier,
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        assert bus.connects == 1

        await bus.drop()  # the backbone connection closes

        await _wait_for(lambda: bus.subscribes >= 2)  # reader reconnected
        assert bus.connects == 2
        # The whole point: the reader task survives a transient disconnect.
        assert not task.done()

        # After reconnect, a broadcast from another server is still delivered.
        await bus.push(["policy_data"], {"x": 1}, notifier_id="other-server")
        await _wait_for(lambda: notifier.notified)
        assert notifier.notified[0][0] == ["policy_data"]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_reader_gives_up_after_max_retries():
    bus = FakeBus(fail_connect=True)
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_max_retries=3,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )
    task = await broadcaster.start_reader_task()
    # Exhausting retries completes the task cleanly (no escaping exception), which lets
    # the existing ignore_broadcaster_disconnected=False path restart the worker.
    await asyncio.wait_for(task, timeout=2)
    assert task.done()
    assert task.exception() is None
    assert bus.connects == 3


@pytest.mark.asyncio
async def test_stock_broadcaster_reader_dies_on_drop():
    # Negative control: the unpatched EventBroadcaster reader completes on a single
    # backbone drop and never reconnects — the bug this change fixes.
    bus = FakeBus()
    broadcaster = EventBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
    )
    task = await broadcaster.start_reader_task()
    await _wait_for(lambda: bus.subscribes >= 1)

    await bus.drop()

    await asyncio.wait_for(task, timeout=2)
    assert task.done()
    assert bus.connects == 1  # never reconnected


def test_backoff_is_bounded():
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        reconnect_backoff_min=0.5,
        reconnect_backoff_max=10.0,
    )
    delays = [broadcaster._backoff_seconds(attempt) for attempt in range(0, 25)]
    assert all(0.0 <= delay <= 10.0 for delay in delays)
    assert max(delays) > 0
