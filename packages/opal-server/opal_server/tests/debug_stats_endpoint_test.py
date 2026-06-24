from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from opal_server.debug_stats import register_internal_stats_route


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
