import pytest
from opal_server.pubsub_resilience import SafeConnectionManager


class _FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.closed_code = None

    async def accept(self):
        self.accepted = True

    async def close(self, code: int = 1000):
        self.closed_code = code


def test_disconnect_unknown_socket_does_not_raise():
    manager = SafeConnectionManager()
    # A socket that was never connected must not raise on disconnect.
    manager.disconnect(object())


def test_double_disconnect_is_idempotent():
    manager = SafeConnectionManager()
    websocket = object()
    manager.active_connections.append(websocket)

    manager.disconnect(websocket)
    assert websocket not in manager.active_connections

    # The upstream ConnectionManager would raise ValueError('list.remove(x): x not in
    # list') here; SafeConnectionManager must swallow it.
    manager.disconnect(websocket)
    assert websocket not in manager.active_connections


@pytest.mark.asyncio
async def test_connect_then_double_disconnect():
    manager = SafeConnectionManager()
    websocket = _FakeWebSocket()

    await manager.connect(websocket)
    assert websocket.accepted
    assert websocket in manager.active_connections

    manager.disconnect(websocket)
    manager.disconnect(websocket)
    assert websocket not in manager.active_connections


@pytest.mark.asyncio
async def test_close_all_staggered_closes_every_connection():
    manager = SafeConnectionManager()
    sockets = [_FakeWebSocket() for _ in range(4)]
    for websocket in sockets:
        await manager.connect(websocket)

    # No jitter sleeps in the test.
    closed = await manager.close_all_staggered(min_interval=0, max_interval=0)

    assert closed == 4
    # 1012 = "Service Restart" — tells the client to reconnect (and re-reconcile).
    assert all(websocket.closed_code == 1012 for websocket in sockets)


@pytest.mark.asyncio
async def test_close_all_staggered_on_empty_is_noop():
    manager = SafeConnectionManager()
    assert await manager.close_all_staggered(min_interval=0, max_interval=0) == 0
