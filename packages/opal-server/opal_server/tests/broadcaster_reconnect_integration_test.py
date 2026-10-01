"""Integration test for the reconnecting broadcaster against the real
``PubSubEndpoint.main_loop``.

In production every client websocket waits (``ignore_broadcaster_disconnected=False``)
on a single shared broadcaster reader task. When the backbone drops, the stock reader
completes and ``PubSubEndpoint.main_loop`` cancels the client's websocket loop — the
mechanism behind the fleet-wide drop storm. This test wires the real ``PubSubEndpoint``
to a fault-injectable in-memory backbone and asserts:

* with ``ReconnectingBroadcaster`` the client loop is NOT cancelled across a backbone
  outage (the reader stays pending and reconnects), and
* (negative control) with the stock ``EventBroadcaster`` the client loop IS cancelled,
  reproducing the bug.

It runs fully in-process, driving the actual ``PubSubEndpoint`` / ``WebsocketRPCEndpoint``
code paths with a fake websocket, so it is deterministic and needs no real backbone.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from fastapi_websocket_pubsub import EventBroadcaster, PubSubEndpoint
from fastapi_websocket_pubsub.websocket_rpc_event_notifier import (
    WebSocketRpcEventNotifier,
)
from opal_server.pubsub_resilience import ReconnectingBroadcaster

_END = object()


class FaultyBus:
    """A fault-injectable in-memory backbone shared by all channel
    instances."""

    def __init__(self):
        self.faulted = False
        self.connects = 0
        self.subscribes = 0
        self._subscriber_queues = []

    def channel_factory(self, _url):
        return _FaultyChannel(self)

    def fault(self):
        """Drop the backbone: end active reads and refuse new connections."""
        self.faulted = True
        for queue in list(self._subscriber_queues):
            queue.put_nowait(_END)

    def recover(self):
        self.faulted = False


class _FaultyChannel:
    def __init__(self, bus):
        self._bus = bus

    async def connect(self):
        self._bus.connects += 1
        if self._bus.faulted:
            raise ConnectionError("backbone is faulted")

    async def disconnect(self):
        pass

    def subscribe(self, channel):
        return _FaultySubscription(self._bus)


class _FaultySubscription:
    def __init__(self, bus):
        self._bus = bus
        self._queue = asyncio.Queue()

    async def __aenter__(self):
        self._bus.subscribes += 1
        self._bus._subscriber_queues.append(self._queue)
        return _FaultySubscriber(self._queue)

    async def __aexit__(self, *exc):
        if self._queue in self._bus._subscriber_queues:
            self._bus._subscriber_queues.remove(self._queue)
        return False


class _FaultySubscriber:
    def __init__(self, queue):
        self._queue = queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is _END:
            raise StopAsyncIteration
        return item


class FakeWebSocket:
    """A websocket whose receive blocks until close — an idle, connected
    client."""

    def __init__(self):
        self.client = SimpleNamespace(host="test-client", port=12345)
        self._closed = asyncio.Event()

    async def accept(self):
        pass

    async def send_text(self, data):
        pass

    async def send_bytes(self, data):
        pass

    async def receive_text(self):
        await self._closed.wait()
        raise WebSocketDisconnect()

    async def receive_bytes(self):
        await self._closed.wait()
        raise WebSocketDisconnect()

    async def close(self, code: int = 1000):
        self._closed.set()


async def _wait_for(predicate, timeout=3.0):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met within timeout")


async def _serve_one_client(endpoint, websocket):
    return asyncio.create_task(endpoint.main_loop(websocket))


async def _shutdown(websocket, client_task):
    await websocket.close()
    client_task.cancel()
    try:
        await client_task
    except (asyncio.CancelledError, Exception):
        pass


@pytest.mark.asyncio
async def test_client_not_cancelled_when_backbone_drops_with_reconnect():
    notifier = WebSocketRpcEventNotifier()
    bus = FaultyBus()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=notifier,
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0.01,
        reconnect_backoff_max=0.05,
    )
    endpoint = PubSubEndpoint(
        notifier=notifier,
        broadcaster=broadcaster,
        ignore_broadcaster_disconnected=False,
    )
    websocket = FakeWebSocket()
    client_task = await _serve_one_client(endpoint, websocket)
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        connects_before = bus.connects

        bus.fault()  # backbone outage
        await asyncio.sleep(0.3)
        # The client websocket loop must survive the outage...
        assert not client_task.done()
        # ...because the reader kept trying to reconnect instead of dying.
        assert bus.connects > connects_before

        bus.recover()
        await _wait_for(lambda: bus.subscribes >= 2)  # reader reconnected
        assert not client_task.done()
    finally:
        await _shutdown(websocket, client_task)


@pytest.mark.asyncio
async def test_client_cancelled_when_backbone_drops_without_reconnect():
    # Negative control: the stock EventBroadcaster reproduces the production bug — the
    # shared reader task completes on a backbone drop and the client loop is cancelled.
    notifier = WebSocketRpcEventNotifier()
    bus = FaultyBus()
    broadcaster = EventBroadcaster(
        "memory://",
        notifier=notifier,
        channel="test",
        broadcast_type=bus.channel_factory,
    )
    endpoint = PubSubEndpoint(
        notifier=notifier,
        broadcaster=broadcaster,
        ignore_broadcaster_disconnected=False,
    )
    websocket = FakeWebSocket()
    client_task = await _serve_one_client(endpoint, websocket)
    try:
        await _wait_for(lambda: bus.subscribes >= 1)

        bus.fault()
        # The client loop ends (gets cancelled) because the shared reader died.
        await _wait_for(lambda: client_task.done(), timeout=3)
        assert client_task.done()
        assert bus.connects == 1  # never reconnected
    finally:
        await _shutdown(websocket, client_task)
