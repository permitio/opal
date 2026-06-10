"""Broadcaster-aware /healthcheck behavior under a simulated database kill.

These tests drive a real ``ReconnectingBroadcaster`` reader against an in-memory,
fault-injectable backbone (``InMemoryBackbone`` from the consistency test, where
``fault()`` == "kill the DB" and ``recover()`` restores it) and assert the
*non-flapping* property the probe exists to provide:

* A **transient** backbone/DB kill keeps the reader pending (it reconnects), so
  ``is_reader_healthy()`` stays True and /healthcheck stays 200 — no needless pod
  restart during a normal blip.
* A backbone/DB kill the reader **gives up on** (reconnect attempts exhausted →
  reader task done) flips ``is_reader_healthy()`` to False and /healthcheck to 503,
  so k8s can act.
* After **recovery** the reader reconnects and health returns to True / 200.

The route-level assertions tie these predicate states to the real OpalServer
``/healthcheck`` endpoint, proving the wiring and not just the predicate.
"""
import asyncio
import contextlib

import pytest
from fastapi_websocket_pubsub.websocket_rpc_event_notifier import (
    WebSocketRpcEventNotifier,
)
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.server import OpalServer
from opal_server.tests.broadcaster_consistency_integration_test import InMemoryBackbone
from starlette.testclient import TestClient

CHANNEL = "EventNotifier"


async def _wait_for(predicate, timeout=5.0):
    """Poll ``predicate`` until it is truthy or ``timeout`` elapses.

    Copied from the consistency test for determinism: prefer polling a condition
    over fixed sleeps so the tests are fast and not timing-fragile.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def _make_live_broadcaster(bus, **kwargs):
    """A ReconnectingBroadcaster wired to ``bus`` with small/zero backoff.

    ``_listen_count`` is set to 1 to represent "clients depend on the reader" —
    that is the state in which ``is_reader_healthy()`` reflects the reader task.
    """
    broadcaster = ReconnectingBroadcaster(
        "memory://",
        notifier=WebSocketRpcEventNotifier(),
        channel=CHANNEL,
        broadcast_type=bus.factory,
        reconnect_backoff_min=0.01,
        reconnect_backoff_max=0.02,
        **kwargs,
    )
    broadcaster._listen_count = 1
    return broadcaster


async def _cancel_reader(task):
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


@contextlib.contextmanager
def _pending_reader_task():
    """Yield a never-completing task standing in for a live, pending reader.

    The task lives on a dedicated loop that stays open for the body and is
    cancelled, drained, and closed on exit — so there is no "Task was destroyed
    but it is pending" warning. The route only reads ``is_reader_healthy()`` (a
    synchronous attribute check), so the task itself is never awaited by the route.
    """
    loop = asyncio.new_event_loop()
    task = loop.create_task(asyncio.Event().wait())
    try:
        yield task
    finally:
        task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        loop.close()


def _done_task():
    """An already-completed task standing in for a reader that gave up retrying."""
    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(asyncio.sleep(0))
        loop.run_until_complete(task)
        return task
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_healthcheck_stays_ok_through_transient_db_kill():
    """A transient DB kill must NOT flip the reader to unhealthy.

    ``reconnect_max_retries=0`` (retry forever): the reader keeps reconnecting, so
    its task stays pending across the kill and ``is_reader_healthy()`` stays True
    throughout — the property that stops the probe from flapping the pod during a
    normal backbone blip. After recovery the reader re-subscribes and stays healthy.
    """
    bus = InMemoryBackbone()
    broadcaster = _make_live_broadcaster(bus, reconnect_max_retries=0)
    reader = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscriber_count() >= 1)
        assert broadcaster.is_reader_healthy() is True

        # Kill the DB: connect()/publish() now raise and active subscribers end.
        bus.fault()
        await _wait_for(lambda: bus.subscriber_count() == 0)
        # Give the reconnect loop time to spin (it cannot reconnect while faulted).
        await asyncio.sleep(0.1)

        # The crucial non-flap assertion: the reader is still pending and healthy
        # mid-reconnect, so /healthcheck would stay 200, not restart the pod.
        assert not reader.done()
        assert broadcaster.is_reader_healthy() is True

        # Recover the DB: the reader re-subscribes and remains healthy.
        bus.recover()
        await _wait_for(lambda: bus.subscriber_count() >= 1)
        assert not reader.done()
        assert broadcaster.is_reader_healthy() is True
    finally:
        await _cancel_reader(reader)


@pytest.mark.asyncio
async def test_healthcheck_goes_503_when_reconnect_gives_up():
    """A permanent DB kill that exhausts retries must flip the reader to unhealthy.

    ``reconnect_max_retries=3`` with tiny backoff: a permanent fault drives the
    reconnect loop to give up; the reader task completes (done). With listeners
    present that is exactly the wedged state ``is_reader_healthy()`` reports False
    for, which is what makes /healthcheck return 503.
    """
    bus = InMemoryBackbone()
    broadcaster = _make_live_broadcaster(bus, reconnect_max_retries=3)
    reader = await broadcaster.start_reader_task()
    try:
        await _wait_for(lambda: bus.subscriber_count() >= 1)
        assert broadcaster.is_reader_healthy() is True

        # Kill the DB permanently (never recover): every reconnect attempt fails.
        bus.fault()

        # The reader exhausts its retries and completes cleanly (no escaping error).
        await asyncio.wait_for(reader, timeout=5)
        assert reader.done()
        assert reader.exception() is None
        # Listeners still depend on a now-dead reader -> unhealthy -> 503.
        assert broadcaster.is_reader_healthy() is False
    finally:
        await _cancel_reader(reader)


def _build_server():
    return OpalServer(
        init_policy_watcher=False,
        broadcaster_uri=None,
        enable_jwks_endpoint=False,
    )


def test_route_healthcheck_200_when_reader_pending():
    """Route-level: reader pending (healthy) -> GET /healthcheck == 200.

    Uses a deterministic never-completing task for the pending reader (what the
    route reads is the synchronous ``is_reader_healthy()`` state check); the live
    fault/reconnect/give-up path is exercised by the async tests above.
    """
    server = _build_server()
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=server.pubsub.notifier, channel=CHANNEL
    )
    broadcaster._listen_count = 1
    with _pending_reader_task() as pending:
        broadcaster._subscription_task = pending
        server.pubsub.broadcaster = broadcaster

        assert broadcaster.is_reader_healthy() is True
        client = TestClient(server.app)
        assert client.get("/healthcheck").status_code == 200


def test_route_healthcheck_503_when_reader_gave_up():
    """Route-level: reader done (gave up) -> GET /healthcheck == 503.

    Uses an already-completed task for the "gave up" reader; the route reads the
    synchronous ``is_reader_healthy()`` state, which is False with listeners present
    and a done reader task.
    """
    server = _build_server()
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=server.pubsub.notifier, channel=CHANNEL
    )
    broadcaster._listen_count = 1
    broadcaster._subscription_task = _done_task()
    server.pubsub.broadcaster = broadcaster

    assert broadcaster.is_reader_healthy() is False
    client = TestClient(server.app)
    response = client.get("/healthcheck")
    assert response.status_code == 503
    assert response.json()["broadcaster"] == "unhealthy"
    # Liveness stays up even while readiness fails.
    assert client.get("/").status_code == 200
