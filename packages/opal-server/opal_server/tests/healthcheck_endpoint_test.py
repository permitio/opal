"""End-to-end checks of the broadcaster-aware /healthcheck route.

Verifies the wiring in OpalServer._init_fast_api_app: a wedged
reconnecting broadcaster (listeners present, reader task missing) makes
/healthcheck return 503 so a k8s probe can act, while / stays a trivial
liveness 200.
"""
import contextlib

from opal_server.config import opal_server_config
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.server import OpalServer
from starlette.testclient import TestClient


@contextlib.contextmanager
def _override_config(**overrides):
    saved = {key: getattr(opal_server_config, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(opal_server_config, key, value)
        yield
    finally:
        for key, value in saved.items():
            setattr(opal_server_config, key, value)


def _build_server():
    return OpalServer(
        init_policy_watcher=False,
        broadcaster_uri=None,
        enable_jwks_endpoint=False,
    )


def _wedge(server):
    """Install a reconnecting broadcaster whose reader is wedged (listeners
    present, reader task missing) — the exact state the staging incident got
    stuck in."""
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=server.pubsub.notifier, channel="test"
    )
    broadcaster._listen_count = 1
    broadcaster._subscription_task = None
    server.pubsub.broadcaster = broadcaster


def test_root_and_healthcheck_ok_without_broadcaster():
    client = TestClient(_build_server().app)
    assert client.get("/").status_code == 200
    assert client.get("/healthcheck").status_code == 200


def test_healthcheck_503_when_reader_wedged():
    server = _build_server()
    _wedge(server)
    client = TestClient(server.app)

    response = client.get("/healthcheck")
    assert response.status_code == 503
    assert response.json()["broadcaster"] == "unhealthy"
    # liveness stays up even while readiness is failing
    assert client.get("/").status_code == 200


def test_healthcheck_kill_switch_keeps_it_ok_when_disabled():
    server = _build_server()
    _wedge(server)
    client = TestClient(server.app)
    with _override_config(BROADCAST_HEALTHCHECK_ENABLED=False):
        assert client.get("/healthcheck").status_code == 200
