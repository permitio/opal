"""The INFO lines of a backbone gap, kept until 0.10 runs in production: the
listener's reconnect (failed attempts, time without a subscription), a full
replay buffer (once per fill), and the replay after the gap (replayed, failed
and dropped counts, the gap's length)."""

import asyncio
import re

import pytest
from opal_common.tests.log_capture import capture_records
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.tests.reconnecting_broadcaster_test import (
    FakeBus,
    FakeNotifier,
    _noop_listening_context,
    _wait_for,
)

_DOWN = ConnectionError("backbone down")


def _info(logs, starting_with: str) -> list:
    return [
        r["message"]
        for r in logs.emitted
        if r["level"].name == "INFO" and r["message"].startswith(starting_with)
    ]


def _broadcaster(bus: FakeBus, **kwargs) -> ReconnectingBroadcaster:
    return ReconnectingBroadcaster(
        "memory://",
        notifier=FakeNotifier(),
        channel="test",
        broadcast_type=bus.channel_factory,
        reconnect_backoff_min=0,
        reconnect_backoff_max=0,
        resync_settle_seconds=0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_a_reconnect_after_a_gap_logs_its_attempts_and_time_then_the_replay(
    monkeypatch,
):
    """A sustained session drops, two connects fail, the third holds: one line
    for the reconnect, and the recovery's replay of what was buffered meanwhile
    names the same gap. The first connect logs none.

    Mutation: not stamping the gap's start reads "an unknown time".
    """
    bus = FakeBus()
    broadcaster = _broadcaster(bus)
    monkeypatch.setattr(broadcaster, "get_listening_context", _noop_listening_context)
    with capture_records() as logs:
        task = await broadcaster.start_reader_task()
        try:
            await _wait_for(lambda: bus.subscribes >= 1)
            await bus.push(["policy_data"], {"x": 1}, notifier_id="other-server")
            await _wait_for(lambda: broadcaster._notifier.notified)
            assert _info(logs, "Broadcaster listener subscribed") == []
            bus.fail_connect_times = bus.connects + 2
            await bus.drop()
            await broadcaster._buffer_outbound("policy_data", {"n": 1}, _DOWN)
            await _wait_for(lambda: _info(logs, "Replayed"))
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    [reconnect] = _info(logs, "Broadcaster listener subscribed")
    match = re.fullmatch(
        r"Broadcaster listener subscribed to channel 'test' again after "
        r"(\d+\.\ds) without a subscription and 2 failed attempts",
        reconnect,
    )
    assert match, reconnect
    assert _info(logs, "Replayed") == [
        f"Replayed 1 of 1 buffered broadcasts after a backbone gap of "
        f"{match.group(1)}: 0 failed (kept for the next recovery), 0 dropped (0 by "
        "the full buffer, 0 failed with no room left to keep them, 0 not "
        "serializable)"
    ]


@pytest.mark.asyncio
async def test_a_full_replay_buffer_is_logged_once_per_fill():
    """Two broadcasts over a buffer of two: one line, at the first drop; after
    a replay empties it, the next fill logs again."""
    bus = FakeBus()
    broadcaster = _broadcaster(bus, replay_buffer_size=2)

    with capture_records() as logs:
        for n in range(4):
            await broadcaster._buffer_outbound("policy_data", {"n": n}, _DOWN)
        assert len(_info(logs, "Broadcast replay buffer full")) == 1
        await broadcaster._flush_outbound_buffer()
        for n in range(3):
            await broadcaster._buffer_outbound("policy_data", {"n": n}, _DOWN)

    assert (
        _info(logs, "Broadcast replay buffer full")
        == [
            "Broadcast replay buffer full (2 broadcasts): the oldest are dropped until "
            "the backbone is back"
        ]
        * 2
    )


@pytest.mark.asyncio
async def test_the_replay_line_counts_what_was_replayed_failed_and_dropped():
    """A buffer of three that dropped one at overflow, holding a payload that
    cannot be serialized, replayed over a backbone that fails after one
    publish: 1 replayed, 1 failed and kept, 2 dropped. With no reconnect
    seen, the gap's length is unknown."""
    bus = FakeBus(fail_publish_after=1)
    broadcaster = _broadcaster(bus, replay_buffer_size=3)
    for n in range(4):
        await broadcaster._buffer_outbound("policy_data", {"n": n}, _DOWN)
    broadcaster._outbound_buffer[0] = ("policy_data", object())

    with capture_records() as logs:
        await broadcaster._flush_outbound_buffer()

    assert _info(logs, "Replayed") == [
        "Replayed 1 of 3 buffered broadcasts after a backbone gap of an unknown "
        "time: 1 failed (kept for the next recovery), 2 dropped (1 by the full "
        "buffer, 0 failed with no room left to keep them, 1 not serializable)"
    ]
    assert [d for _, d in broadcaster._outbound_buffer] == [{"n": 3}]


@pytest.mark.asyncio
async def test_an_empty_buffer_logs_no_replay():
    broadcaster = _broadcaster(FakeBus())

    with capture_records() as logs:
        await broadcaster._flush_outbound_buffer()

    assert _info(logs, "Replayed") == []


class _RefillThenFail:
    """A backbone whose replay publishes one broadcast, then, while the second
    is under way, sees two new broadcasts fail and get buffered, then fails
    too."""

    def __init__(self, broadcaster: ReconnectingBroadcaster):
        self._broadcaster = broadcaster
        self.published = []

    def __call__(self, _url):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def publish(self, channel, payload):
        if self.published:
            for n in ("d", "e"):
                await self._broadcaster._buffer_outbound("policy_data", {"n": n}, _DOWN)
            raise ConnectionError("publish failed")
        self.published.append(payload)


@pytest.mark.asyncio
async def test_failed_broadcasts_the_full_buffer_cannot_keep_are_counted_dropped():
    """A buffer of three replayed while two new broadcasts fail: of the two
    that failed to replay, the buffer keeps one, after the two new ones, and
    drops the other. The line says 1 failed and kept, 1 dropped, and the
    buffer-full line is logged.

    Mutation: counting every failed broadcast as kept says 2 failed, 0
    dropped.
    """
    broadcaster = _broadcaster(FakeBus(), replay_buffer_size=3)
    backbone = _RefillThenFail(broadcaster)
    broadcaster._broadcast_type = backbone
    for n in ("a", "b", "c"):
        await broadcaster._buffer_outbound("policy_data", {"n": n}, _DOWN)

    with capture_records() as logs:
        await broadcaster._flush_outbound_buffer()

    assert [d["n"] for _, d in broadcaster._outbound_buffer] == ["c", "d", "e"]
    assert _info(logs, "Replayed") == [
        "Replayed 1 of 3 buffered broadcasts after a backbone gap of an unknown "
        "time: 1 failed (kept for the next recovery), 1 dropped (0 by the full "
        "buffer, 1 failed with no room left to keep them, 0 not serializable)"
    ]
    assert len(_info(logs, "Broadcast replay buffer full")) == 1
