"""Unit tests for ReconnectingBroadcaster.

The tests drive the broadcaster against an in-memory, fault-injectable backbone so
they are deterministic and require no real Postgres/Redis. The key invariant under
test is that a transient backbone disconnect must NOT complete the reader task (which
is what cancels every client websocket in production). The final test is a negative
control: the stock EventBroadcaster reader DOES complete on the same disconnect,
proving these tests actually catch the regression.
"""
import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi_websocket_pubsub import EventBroadcaster
from fastapi_websocket_pubsub.event_broadcaster import BroadcastNotification
from opal_server.pubsub_resilience import (
    FreezablePubSubEndpoint,
    ReconnectingBroadcaster,
)

_END = object()


def _noop_listening_context():
    """Stand-in for the broadcaster's pinned listening context that does
    nothing, so a unit test can exercise the recovery loop without a real
    backbone reader."""

    @asynccontextmanager
    async def _ctx():
        yield

    return _ctx()


class _Event:
    def __init__(self, message):
        self.message = message


class FakeNotifier:
    def __init__(self):
        self.notified = []

    async def notify(self, topics, data, notifier_id=None):
        self.notified.append((list(topics), data, notifier_id))

    def gen_subscriber_id(self):
        # PubSubEndpoint.__init__ mints a server id from the notifier.
        return "fake-subscriber-id"

    async def subscribe(self, *args, **kwargs):
        # The broadcaster's sharing context registers itself on the notifier
        # (EventBroadcaster._subscribe_to_all_topics); a no-op suffices here.
        pass


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
    # A second gap while a recovery is still in flight must not spawn a second recovery;
    # instead it requests a rerun so the in-flight recovery loops once more (F2).
    broadcaster = _make_broadcaster()
    blocker = asyncio.Event()
    broadcaster._recovery_task = asyncio.create_task(blocker.wait())
    broadcaster._tasks.add(broadcaster._recovery_task)
    first = broadcaster._recovery_task
    assert broadcaster._recovery_rerun_requested is False

    broadcaster._schedule_gap_recovery()  # second gap during the in-flight recovery
    assert broadcaster._recovery_task is first  # single-flight: no new recovery task
    assert broadcaster._recovery_rerun_requested is True  # but a rerun is requested

    blocker.set()
    await first


@pytest.mark.asyncio
async def test_recovery_reruns_for_gap_during_late_phase():
    # F2: a gap that lands during the LATE recovery phase (after the flush, while the
    # reconnect hook runs) must still be flushed/resynced by exactly one more loop —
    # not dropped because a recovery was already in flight.
    broadcaster = _make_broadcaster()
    broadcaster._resync_settle_seconds = 0
    fire_count = 0
    release_first_fire = asyncio.Event()

    async def on_reconnect():
        nonlocal fire_count
        fire_count += 1
        if fire_count == 1:
            # A gap arriving during the first recovery's late (fire) phase routes to the
            # in-flight recovery (which is broadcaster._recovery_task) and sets the flag.
            broadcaster._schedule_gap_recovery()
            # Block until the test confirms the rerun was requested mid-iteration.
            await release_first_fire.wait()

    broadcaster.set_reconnect_callback(on_reconnect)
    # Isolate the rerun-loop semantics from the real listening-context pin (which is
    # covered by test_recovery_pins_reader_across_client_recycle).
    broadcaster.get_listening_context = _noop_listening_context

    # Start the recovery through the scheduler so broadcaster._recovery_task is the live
    # task — that is what the nested _schedule_gap_recovery sees as "already in flight".
    broadcaster._schedule_gap_recovery()
    recovery = broadcaster._recovery_task
    await _wait_for(lambda: fire_count == 1)
    # The gap during the late phase requested a rerun on the live recovery.
    assert broadcaster._recovery_rerun_requested is True
    release_first_fire.set()

    await asyncio.wait_for(recovery, timeout=2)
    # The recovery looped exactly once more: the hook fired twice, then settled.
    assert fire_count == 2
    assert broadcaster._recovery_rerun_requested is False


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

    await broadcaster._recover_after_gap()

    assert observed["reader_alive"] is True
    # The pin is released and no client remains, so the reader is cancelled by the
    # listener count reaching zero — drain it.
    if not reader.done():
        reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader


def _count_gap_recoveries(broadcaster) -> list:
    """Replace _schedule_gap_recovery with a no-op counter so a test can assert
    whether a (re)connect treated itself as a gap, without running the real
    recovery machinery."""
    scheduled = []
    broadcaster._schedule_gap_recovery = lambda: scheduled.append(1)
    return scheduled


@pytest.mark.asyncio
async def test_fresh_reader_task_does_not_recover_on_first_connect():
    # F1: gap detection is reader-task-local. When the last client disconnects the
    # upstream cancels the reader and clears _subscription_task; the NEXT client starts a
    # fresh reader task, whose first connect must NOT be treated as a gap (no spurious
    # flush + client-recycling resync). Only a reconnect WITHIN a task's own loop is a gap.
    bus = FakeBus()
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )
    scheduled = _count_gap_recoveries(broadcaster)

    # First reader task: its initial connect is not a gap.
    first = await broadcaster.start_reader_task()
    await _wait_for(lambda: bus.subscribes >= 1)
    assert scheduled == []

    # The last client disconnects: upstream cancels the reader and resets the handle.
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    broadcaster._subscription_task = None

    # A new client arrives: a FRESH reader task starts. Its first connect must NOT
    # schedule a gap recovery, even though a prior connection existed on this instance.
    second = await broadcaster.start_reader_task()
    assert second is not first
    await _wait_for(lambda: bus.subscribes >= 2)
    await asyncio.sleep(0.05)
    assert scheduled == []  # fresh task starts clean — no stale-instance-flag recovery

    try:
        # A real backbone gap WITHIN this task's loop (a drop + reconnect) does recover.
        await bus.drop()
        await _wait_for(lambda: bus.subscribes >= 3)
        await _wait_for(lambda: len(scheduled) == 1)
    finally:
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second


@pytest.mark.asyncio
async def test_flap_loop_counts_toward_give_up():
    # F3(b): a connect-OK / instant-close flap loop must increment the attempt counter
    # (the subscriber never sustains a read), so reconnect_max_retries trips and the
    # reader completes — rather than looping forever because a connect resets the counter.
    bus = FakeBus()
    give_up = []

    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_max_retries=3,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )

    async def on_give_up():
        give_up.append(1)

    broadcaster.set_give_up_callback(on_give_up)

    # Each subscribe connects fine, then the subscriber ends immediately (a flap): the
    # shared read queue is pre-loaded with _END markers, so every session reads one _END
    # and stops without ever sustaining a read. Three such flaps exhaust max_retries=3.
    for _ in range(5):
        await bus.drop()

    task = await broadcaster.start_reader_task()

    # Three sub-threshold sessions exhaust the retry budget and the reader returns.
    await asyncio.wait_for(task, timeout=2)
    assert task.done()
    assert task.exception() is None
    assert give_up == [1]  # the give-up hook fired exactly once (on the returning path)


@pytest.mark.asyncio
async def test_give_up_hook_not_fired_on_cancellation():
    # F3(a): the give-up hook is for give-up (return), NOT clean shutdown (cancellation).
    bus = FakeBus()
    give_up = []
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )

    async def on_give_up():
        give_up.append(1)

    broadcaster.set_give_up_callback(on_give_up)

    task = await broadcaster.start_reader_task()
    await _wait_for(lambda: bus.subscribes >= 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)
    assert give_up == []  # cancellation must not look like a give-up


@pytest.mark.asyncio
async def test_partial_replay_requeue_preserves_drop_oldest():
    # F5: when a transport failure re-enqueues the unsent (older) tail AND concurrent
    # failures refilled the buffer (newer), the bounded deque must drop the OLDEST from
    # the front, keeping order unsent-before-refill — not evict the newest refill.
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        replay_buffer_size=3,
    )
    # Simulate a concurrent refill that landed during the lock-free publish: two newer
    # entries already sit in the buffer when the unsent tail comes back.
    broadcaster._outbound_buffer.append(("policy_data", {"n": "refill-1"}))
    broadcaster._outbound_buffer.append(("policy_data", {"n": "refill-2"}))

    unsent = [("policy_data", {"n": "unsent-1"}), ("policy_data", {"n": "unsent-2"})]
    await broadcaster._requeue_unsent(unsent)

    # maxlen=3: unsent (older) go in front, then refill (newer); overflow drops oldest.
    assert broadcaster._outbound_buffer.maxlen == 3
    assert [data["n"] for _, data in broadcaster._outbound_buffer] == [
        "unsent-2",
        "refill-1",
        "refill-2",
    ]
    # The OLDEST (unsent-1) was dropped from the front, NOT the newest refill.


# ---------------------------------------------------------------------------
# Fleet-consistency freeze (is_backbone_connected + FreezablePubSubEndpoint)
# ---------------------------------------------------------------------------


def _reconnecting(bus, notifier=None):
    return ReconnectingBroadcaster(
        "memory://",
        notifier=notifier or FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
    )


@pytest.mark.asyncio
async def test_is_backbone_connected_tracks_subscription():
    """The flag is False before the reader subscribes, True while subscribed, and
    False again once the reader stops."""
    bus = FakeBus()
    broadcaster = _reconnecting(bus)
    assert not broadcaster.is_backbone_connected()  # not started -> disconnected
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(broadcaster.is_backbone_connected)  # subscribed -> connected
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not broadcaster.is_backbone_connected()  # reader gone -> disconnected


@pytest.mark.asyncio
async def test_is_in_backbone_gap_lifecycle():
    """A GAP is: had a live subscription, lost it, reader still retrying. Neither
    'never started' nor 'never yet connected' nor 'reconnected' is a gap."""
    bus = FakeBus()
    broadcaster = _reconnecting(bus)
    assert not broadcaster.is_in_backbone_gap()  # never started -> not a gap
    task = await broadcaster.start_reader_task()
    try:
        await _wait_for(broadcaster.is_backbone_connected)
        assert not broadcaster.is_in_backbone_gap()  # subscribed -> not a gap

        # Backbone drops and stays unavailable: block re-subscribes, then close the read.
        bus.fail_subscribe_times = 10_000
        await bus.drop()
        await _wait_for(broadcaster.is_in_backbone_gap)  # GAP: had one, lost it

        # Backbone returns: allow re-subscribes -> gap ends.
        bus.fail_subscribe_times = 0
        await _wait_for(lambda: not broadcaster.is_in_backbone_gap())
        assert broadcaster.is_backbone_connected()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_reader_restart_does_not_inherit_gap_state():
    """A RESTARTED reader (previous one cancelled when the last listener left) must
    start with a clean slate: its pre-first-subscribe window is 'never connected',
    not a gap — a first connect fires no resync, so freezing there would LOSE
    publishes rather than defer them."""
    bus = FakeBus()
    broadcaster = _reconnecting(bus)
    task = await broadcaster.start_reader_task()
    await _wait_for(broadcaster.is_backbone_connected)  # session established
    # Last listener leaves: upstream cancels the reader and clears the task slot.
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    broadcaster._subscription_task = None
    # Backbone is down when a new listener restarts the reader.
    bus.fail_subscribe_times = 10_000
    task2 = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscribes >= 2)  # new reader is retrying
        assert not broadcaster.is_in_backbone_gap()  # clean slate: NOT a gap
    finally:
        task2.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task2


def _endpoint(broadcaster, notifier, freeze=True, exempt=()):
    return FreezablePubSubEndpoint(
        broadcaster=broadcaster,
        notifier=notifier,
        freeze_on_disconnect=freeze,
        freeze_exempt_topics=exempt,
    )


def _fabricate_gap(broadcaster):
    """Put a broadcaster into the mid-gap state (had a session, lost it, reader
    pending) without driving a real backbone. Returns the dummy reader task —
    cancel it in the test's cleanup."""
    dummy = asyncio.get_event_loop().create_task(asyncio.sleep(60))
    broadcaster._subscription_task = dummy
    broadcaster._had_backbone_connection = True
    broadcaster._backbone_connected = False
    return dummy


@pytest.mark.asyncio
async def test_should_freeze_matrix():
    """Freeze only when: enabled AND ReconnectingBroadcaster AND mid-GAP AND a
    non-exempt topic. Everything else delegates normally."""
    bus = FakeBus()
    topics = ["policy_data"]

    # never-started reader -> NOT a gap -> no freeze (healthy idle worker must not drop)
    b = _reconnecting(bus)
    assert _endpoint(b, FakeNotifier())._should_freeze(topics) is False
    # reader running but never yet connected (boot / backbone down from the start) -> no
    # freeze: no resync fires on a FIRST connect, so a frozen publish would be lost.
    dummy = _fabricate_gap(b)
    b._had_backbone_connection = False
    try:
        assert _endpoint(b, FakeNotifier())._should_freeze(topics) is False
        # a real gap (had a session, lost it) -> FREEZE
        b._had_backbone_connection = True
        endpoint = _endpoint(b, FakeNotifier())
        assert endpoint._should_freeze(topics) is True
        # exempt topics keep flowing mid-gap: "__" internals and the explicit exempt set
        assert endpoint._should_freeze(["__opal_stats_server_keepalive"]) is False
        assert (
            _endpoint(b, FakeNotifier(), exempt=["webhook"])._should_freeze(["webhook"])
            is False
        )
        # a mixed list containing any non-exempt topic still freezes (consistency wins)
        assert endpoint._should_freeze(["__opal_stats_wakeup", "policy_data"]) is True
        # freeze disabled -> never
        assert (
            _endpoint(b, FakeNotifier(), freeze=False)._should_freeze(topics) is False
        )
        # reconnected -> never
        b._backbone_connected = True
        assert _endpoint(b, FakeNotifier())._should_freeze(topics) is False
        b._backbone_connected = False
    finally:
        dummy.cancel()
    # no broadcaster (single worker) -> never
    assert _endpoint(None, FakeNotifier())._should_freeze(topics) is False
    # stock (non-reconnecting) broadcaster -> never (legacy drop-on-disconnect path)
    stock = EventBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
    )
    assert _endpoint(stock, FakeNotifier())._should_freeze(topics) is False


@pytest.mark.asyncio
async def test_publish_is_suppressed_during_gap():
    """Mid-gap, publish must not deliver to clients at all (notifier untouched);
    after the gap the next publish delivers and resets the episode counter."""
    notifier = FakeNotifier()
    b = _reconnecting(FakeBus())
    dummy = _fabricate_gap(b)
    endpoint = _endpoint(b, notifier)
    try:
        await endpoint.publish(["policy_data"], {"x": 1})
        await endpoint.publish(["policy_data"], {"x": 2})
        assert notifier.notified == []  # frozen: nothing reached the clients
        assert endpoint._frozen_in_episode == 2
        # gap ends -> publish flows again and the episode counter resets
        b._backbone_connected = True
        await endpoint.publish(["policy_data"], {"x": 3})
        assert [d for _, d, _ in notifier.notified] == [{"x": 3}]
        assert endpoint._frozen_in_episode == 0
    finally:
        dummy.cancel()


@pytest.mark.asyncio
async def test_publish_delivers_when_not_freezing():
    """With no broadcaster (nothing to freeze), publish delegates and delivers."""
    notifier = FakeNotifier()
    endpoint = _endpoint(None, notifier)
    await endpoint.publish(["policy_data"], {"x": 1})
    assert notifier.notified and notifier.notified[0][0] == ["policy_data"]


def test_notify_alias_is_frozen():
    """The library aliases ``notify = publish`` at class level (binding the BASE
    publish); the subclass must re-bind it or ``endpoint.notify(...)`` bypasses
    the freeze gate."""
    assert FreezablePubSubEndpoint.notify is FreezablePubSubEndpoint.publish
