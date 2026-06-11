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

    def __init__(
        self,
        fail_connect=False,
        fail_connect_times=0,
        fail_subscribe_times=0,
        connect_gate=None,
        fail_publish_after=None,
    ):
        self.fail_connect = fail_connect  # permanently refuse to connect
        self.fail_connect_times = (
            fail_connect_times  # refuse the first N connects, then succeed
        )
        self.fail_subscribe_times = fail_subscribe_times  # fail the first N subscribes
        self.connect_gate = (
            connect_gate  # asyncio.Event; if set, connect awaits it (slow connect)
        )
        # publish raises once this many payloads have published (transport fails mid-drain)
        self.fail_publish_after = fail_publish_after
        self.connects = 0
        self.subscribes = 0
        self.disconnects = 0
        self.published = []  # payloads published via the replay/flush path
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
        if self._bus.connect_gate is not None:
            await self._bus.connect_gate.wait()
        if self._bus.fail_connect or self._bus.connects <= self._bus.fail_connect_times:
            raise ConnectionError("backbone refused connection")

    async def disconnect(self):
        self._bus.disconnects += 1

    def subscribe(self, channel):
        return _FakeSubscription(self._bus)

    # The replay/flush path uses the channel as an async context manager and publishes.
    async def __aenter__(self):
        if self._bus.fail_connect:
            raise ConnectionError("backbone down")
        return self

    async def __aexit__(self, *exc):
        return False

    async def publish(self, channel, payload):
        if (
            self._bus.fail_publish_after is not None
            and len(self._bus.published) >= self._bus.fail_publish_after
        ):
            raise ConnectionError("publish failed")
        self._bus.published.append(payload)


class _FakeSubscription:
    def __init__(self, bus):
        self._bus = bus

    async def __aenter__(self):
        self._bus.subscribes += 1
        if self._bus.subscribes <= self._bus.fail_subscribe_times:
            raise ConnectionError("subscribe failed")
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


def _make_broadcaster():
    return ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
    )


def test_is_reader_healthy_idle_when_no_listeners():
    # No clients depend on the reader; its absence is expected idleness, not a fault.
    broadcaster = _make_broadcaster()
    broadcaster._listen_count = 0
    broadcaster._subscription_task = None
    assert broadcaster.is_reader_healthy() is True


@pytest.mark.asyncio
async def test_is_reader_healthy_with_live_pending_reader():
    # Listeners present and the reader is a live, pending task (this also models the
    # mid-reconnect state ReconnectingBroadcaster keeps pending across a backbone gap).
    broadcaster = _make_broadcaster()
    broadcaster._listen_count = 1
    task = asyncio.create_task(asyncio.sleep(60))
    broadcaster._subscription_task = task
    try:
        assert broadcaster.is_reader_healthy() is True
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_is_reader_healthy_false_when_reader_missing():
    # Listeners present but the reader task is None: leaked listen-count / never-started.
    broadcaster = _make_broadcaster()
    broadcaster._listen_count = 1
    broadcaster._subscription_task = None
    assert broadcaster.is_reader_healthy() is False


@pytest.mark.asyncio
async def test_is_reader_healthy_false_when_reader_done():
    # Listeners present but the reader task completed: it crashed or gave up retrying.
    broadcaster = _make_broadcaster()
    broadcaster._listen_count = 1

    async def _noop():
        return None

    task = asyncio.create_task(_noop())
    await task
    broadcaster._subscription_task = task
    assert task.done()
    assert broadcaster.is_reader_healthy() is False


@pytest.mark.asyncio
async def test_is_reader_healthy_false_when_reader_cancelled():
    # A cancelled reader is also "done" — the wedged state after a clean shutdown
    # of the reader while listeners somehow remain.
    broadcaster = _make_broadcaster()
    broadcaster._listen_count = 1
    task = asyncio.create_task(asyncio.sleep(60))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    broadcaster._subscription_task = task
    assert task.done()
    assert broadcaster.is_reader_healthy() is False


@pytest.mark.asyncio
async def test_reader_recovers_after_transient_connect_failures():
    # Flaky reconnect: the first two reconnect attempts fail, the third succeeds. With
    # max_retries=0 (retry forever) the reader must recover, not give up or die.
    bus = FakeBus(fail_connect_times=2)
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
        assert bus.connects >= 3  # two failures, then a successful connect
        assert not task.done()
        # Delivery resumes once connected.
        await bus.push(["policy_data"], {"x": 1}, notifier_id="other-server")
        await _wait_for(lambda: notifier.notified)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_reader_survives_slow_connect():
    # A slow (but not failed) backbone connect must keep the reader pending. Completing
    # the reader task is exactly what cancels every client websocket in production, so a
    # slow connection must never be mistaken for a dead reader.
    gate = asyncio.Event()
    bus = FakeBus(connect_gate=gate)
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.connects >= 1)  # connect started, but gated (slow)
        await asyncio.sleep(0.05)
        assert not task.done()  # still pending mid-connect
        assert bus.subscribes == 0  # not subscribed until the connect completes
        assert (
            broadcaster.is_reader_healthy() is True
        )  # healthy while connecting slowly
        gate.set()  # the slow connection finally completes
        await _wait_for(lambda: bus.subscribes >= 1)
        assert not task.done()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_reader_reconnects_when_subscribe_fails():
    # connect succeeds but subscribe fails once (a partial connection). The reader must
    # treat it like any backbone error and reconnect, then deliver.
    bus = FakeBus(fail_subscribe_times=1)
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
        await _wait_for(
            lambda: bus.subscribes >= 2
        )  # first subscribe failed, then retried
        assert not task.done()
        await bus.push(["policy_data"], {"x": 1}, notifier_id="other-server")
        await _wait_for(lambda: notifier.notified)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_buffer_overflow_drops_oldest():
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=FakeNotifier(), channel="test", replay_buffer_size=2
    )
    error = ConnectionError("backbone down")
    await broadcaster._buffer_outbound("policy_data", {"n": 1}, error)
    await broadcaster._buffer_outbound("policy_data", {"n": 2}, error)
    assert len(broadcaster._outbound_buffer) == 2

    await broadcaster._buffer_outbound("policy_data", {"n": 3}, error)  # over capacity
    assert len(broadcaster._outbound_buffer) == 2
    # The oldest entry ({"n": 1}) was dropped by the bounded deque.
    assert [data for _, data in broadcaster._outbound_buffer] == [{"n": 2}, {"n": 3}]


@pytest.mark.asyncio
async def test_buffering_disabled_when_size_is_zero():
    # replay_buffer_size=0 disables buffering entirely; the resync is then the only
    # recovery path, so nothing is retained here.
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=FakeNotifier(), channel="test", replay_buffer_size=0
    )
    await broadcaster._buffer_outbound("policy_data", {"n": 1}, ConnectionError("down"))
    assert len(broadcaster._outbound_buffer) == 0


@pytest.mark.asyncio
async def test_flush_replays_buffered_broadcasts():
    bus = FakeBus()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        replay_buffer_size=10,
    )
    error = ConnectionError("backbone down")
    await broadcaster._buffer_outbound("policy_data", {"n": 1}, error)
    await broadcaster._buffer_outbound("policy_data", {"n": 2}, error)

    await broadcaster._flush_outbound_buffer()

    assert len(bus.published) == 2  # both replayed to the backbone
    assert len(broadcaster._outbound_buffer) == 0  # buffer drained


@pytest.mark.asyncio
async def test_flush_drops_unserializable_buffered_broadcast():
    bus = FakeBus()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        replay_buffer_size=10,
    )
    # A poison payload that cannot be serialized must be dropped, not wedge the buffer.
    broadcaster._outbound_buffer.append(("policy_data", object()))
    broadcaster._outbound_buffer.append(("policy_data", {"n": 1}))

    await broadcaster._flush_outbound_buffer()

    assert len(broadcaster._outbound_buffer) == 0  # poison dropped, good one sent
    assert len(bus.published) == 1  # only the serializable broadcast was published


@pytest.mark.asyncio
async def test_shutdown_cancels_pending_child_tasks():
    # On clean shutdown (reader cancellation) any in-flight notify/recovery child task
    # must be cancelled too, so the worker does not leak tasks.
    bus = FakeBus()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )
    task = await broadcaster.start_reader_task()
    await _wait_for(lambda: bus.subscribes >= 1)
    child = asyncio.create_task(asyncio.sleep(60))
    broadcaster._tasks.add(child)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await _wait_for(lambda: child.done())
    assert child.cancelled()


@pytest.mark.asyncio
async def test_skips_own_broadcasts():
    # A broadcast tagged with our own notifier id must not be re-delivered to our local
    # notifier (it was already delivered locally when first published).
    notifier = FakeNotifier()
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=notifier, channel="test"
    )
    own = BroadcastNotification(
        notifier_id=broadcaster._id, topics=["policy_data"], data={"x": 1}
    )
    await broadcaster._handle_broadcast_event(_Event(own.json()))
    assert notifier.notified == []

    other = BroadcastNotification(
        notifier_id="other-server", topics=["policy_data"], data={"x": 2}
    )
    await broadcaster._handle_broadcast_event(_Event(other.json()))
    await _wait_for(lambda: notifier.notified)
    assert notifier.notified[0][0] == ["policy_data"]


@pytest.mark.asyncio
async def test_flush_partial_replay_requeues_unsent():
    # Transport fails after the first publish: the unsent tail must be re-buffered (in
    # order, at the front) for the next recovery, and the sent item must not re-send.
    bus = FakeBus(fail_publish_after=1)
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        replay_buffer_size=10,
    )
    error = ConnectionError("backbone down")
    await broadcaster._buffer_outbound("policy_data", {"n": 1}, error)
    await broadcaster._buffer_outbound("policy_data", {"n": 2}, error)
    await broadcaster._buffer_outbound("policy_data", {"n": 3}, error)

    await broadcaster._flush_outbound_buffer()

    assert (
        len(bus.published) == 1
    )  # only the first got through before the transport failed
    assert [data for _, data in broadcaster._outbound_buffer] == [{"n": 2}, {"n": 3}]

    # The backbone heals; a second flush drains the rest without re-sending {"n": 1}.
    bus.fail_publish_after = None
    await broadcaster._flush_outbound_buffer()
    assert len(bus.published) == 3
    assert len(broadcaster._outbound_buffer) == 0


@pytest.mark.asyncio
async def test_single_flight_recovery_dedupes():
    # A second gap while a recovery is still in flight must not spawn a second recovery.
    broadcaster = _make_broadcaster()
    blocker = asyncio.Event()
    broadcaster._recovery_task = asyncio.create_task(blocker.wait())
    broadcaster._tasks.add(broadcaster._recovery_task)
    first = broadcaster._recovery_task

    broadcaster._schedule_gap_recovery()  # second gap during the in-flight recovery
    assert broadcaster._recovery_task is first  # single-flight: no new recovery task

    blocker.set()
    await first


@pytest.mark.asyncio
async def test_reader_recovers_within_max_retries():
    # max_retries=5 but only 3 transient failures, then success: the reader recovers and
    # resets its attempt counter (a later drop gets the full budget again, not give-up).
    bus = FakeBus(fail_connect_times=3)
    notifier = FakeNotifier()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=notifier,
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_max_retries=5,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 1)
        assert bus.connects >= 4  # 3 failures + a success
        assert not task.done()
        await bus.push(["policy_data"], {"x": 1}, notifier_id="other-server")
        await _wait_for(lambda: notifier.notified)
        # Counter reset: a later drop gets the full retry budget again.
        await bus.drop()
        await _wait_for(lambda: bus.subscribes >= 2)
        assert not task.done()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_recovery_pins_reader_across_client_recycle():
    # The resync closes every client (driving the client-held listen count to 0), but
    # _recover_after_gap pins its own listening context for the whole recovery, so the
    # reader must NOT be cancelled while the recycle happens.
    bus = FakeBus()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        resync_settle_seconds=0,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )
    # One connected client holds the listening context (this also starts the reader).
    client_ctx = broadcaster.get_listening_context()
    await client_ctx.__aenter__()
    reader = broadcaster.get_reader_task()
    await _wait_for(lambda: bus.subscribes >= 1)

    observed = {}

    async def on_reconnect():
        # The resync closes the only client: drop its listening context.
        await client_ctx.__aexit__(None, None, None)
        # The pin in _recover_after_gap must hold the count, keeping the reader alive.
        observed["reader_alive"] = not reader.done()

    broadcaster.set_reconnect_callback(on_reconnect)
    broadcaster._had_prior_connection = True

    await broadcaster._recover_after_gap()

    assert observed["reader_alive"] is True
    # The pin is released and no client remains, so the reader is cancelled by the
    # listener count reaching zero — drain it.
    if not reader.done():
        reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader
