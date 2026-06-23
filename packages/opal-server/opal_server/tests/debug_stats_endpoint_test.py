from fastapi import FastAPI
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
