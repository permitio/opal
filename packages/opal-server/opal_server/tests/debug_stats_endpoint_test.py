import contextlib

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from opal_server.config import opal_server_config
from opal_server.debug_stats import register_internal_stats_route
from opal_server.server import OpalServer


def _app_with_flag(enabled: bool) -> FastAPI:
    app = FastAPI()
    register_internal_stats_route(app, enabled=enabled)
    return app


def test_endpoint_absent_when_disabled():
    client = TestClient(_app_with_flag(False))
    assert client.get("/internal/git-fetcher-cache-stats").status_code == 404


def test_endpoint_present_when_enabled():
    client = TestClient(_app_with_flag(True))
    resp = client.get("/internal/git-fetcher-cache-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"repo_locks", "repos", "repos_last_fetched", "rss_kb"}


def test_endpoint_applies_passed_dependencies():
    """A route dependency (e.g. the server's authenticator) is enforced.

    Mirrors how server.py wires the real JWTAuthenticator: when
    verification is enabled the dependency rejects unauthenticated
    reads; when disabled it is a no-op (covered by the test above, which
    passes no dependency).
    """

    def _deny():
        raise HTTPException(status_code=401, detail="unauthorized")

    app = FastAPI()
    register_internal_stats_route(app, enabled=True, dependencies=[Depends(_deny)])
    resp = TestClient(app).get("/internal/git-fetcher-cache-stats")
    assert resp.status_code == 401


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


def _build_server() -> OpalServer:
    return OpalServer(
        init_policy_watcher=False,
        broadcaster_uri=None,
        enable_jwks_endpoint=False,
    )


def test_server_wiring_mounts_endpoint_when_flag_enabled():
    """The real OpalServer app mounts the route when DEBUG_INTERNAL_STATS is
    on.

    The tests above exercise register_internal_stats_route() on a bare
    FastAPI app; this one covers the wiring in server.py itself —
    without it, removing the register_internal_stats_route() call from
    _init_fast_api_app would leave every unit test green.
    """
    with _override_config(DEBUG_INTERNAL_STATS=True):
        client = TestClient(_build_server().app)
        resp = client.get("/internal/git-fetcher-cache-stats")
    assert resp.status_code == 200
    assert set(resp.json()) == {"repo_locks", "repos", "repos_last_fetched", "rss_kb"}


def test_server_wiring_omits_endpoint_when_flag_disabled():
    with _override_config(DEBUG_INTERNAL_STATS=False):
        client = TestClient(_build_server().app)
        assert client.get("/internal/git-fetcher-cache-stats").status_code == 404
