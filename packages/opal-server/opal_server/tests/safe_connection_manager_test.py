import pytest
from opal_server.pubsub_resilience import SafeConnectionManager


class _FakeWebSocket:
    def __init__(self):
        self.accepted = False

    async def accept(self):
        self.accepted = True


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
