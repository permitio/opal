"""The missing-scope webhook.

With OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL set, a request for a scope
that is not stored makes the worker POST {"scope_id", "route",
"seen_at"} to that URL, with OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN as
a Bearer token: at most once per scope per five minutes per worker, in
a task of its own that the request does not wait for, with a five-second
timeout and no retry, counted by outcome in
opal_server.scopes.missing_scope_webhook.
The token is never logged; the URL is logged masked.

The receiver is a real HTTP server on localhost.
"""

import asyncio
import datetime
import socket
import time
from typing import Callable, List

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opal_common.monitoring import metrics
from opal_common.tests.redaction_fixtures import capture_logs
from opal_server.config import opal_server_config
from opal_server.scopes import missing_scope
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError

pytestmark = pytest.mark.fetch_backend("cli")

_TOKEN = "hunter2-webhook-token"
_OUTCOMES = "opal_server.scopes.missing_scope_webhook"


class _Receiver:
    """Records each POST before it answers ``status`` after ``delay``."""

    def __init__(self) -> None:
        self.posts: List[dict] = []
        self.delay = 0.0
        self.status = 204
        self.url = ""
        self._runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        self.posts.append(
            {
                "path": request.path_qs,
                "authorization": request.headers.get("Authorization"),
                "content_type": request.content_type,
                "body": await request.json(),
            }
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        return web.Response(status=self.status)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/{path:.*}", self._handle)
        # A held answer ends with its client, and a stop does not wait for it.
        # No access log: it would write the URL the server was posted to.
        self._runner = web.AppRunner(
            app, handler_cancellation=True, shutdown_timeout=1.0, access_log=None
        )
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        port = self._runner.addresses[0][1]
        self.origin = f"http://127.0.0.1:{port}"
        self.url = f"{self.origin}/missing"

    async def stop(self) -> None:
        await self._runner.cleanup()


@pytest_asyncio.fixture
async def receiver(monkeypatch):
    server = _Receiver()
    await server.start()
    monkeypatch.setattr(
        opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", server.url
    )
    monkeypatch.setattr(
        opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", _TOKEN
    )
    yield server
    await server.stop()


@pytest.fixture(autouse=True)
def _not_found(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "not_found")
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", None)


@pytest.fixture
def counted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics, "increment", lambda metric, tags=None: calls.append((metric, tags))
    )
    return calls


@pytest.fixture
def clock(monkeypatch):
    """The reporter's clock, moved by hand."""
    now = [1000.0]
    monkeypatch.setattr(missing_scope, "_now", lambda: now[0])
    return now


def _outcomes(counted) -> List[str]:
    return [tags["outcome"] for metric, tags in counted if metric == _OUTCOMES]


async def _until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        await asyncio.sleep(0.01)


class _Scopes:
    async def get(self, scope_id):
        raise ScopeNotFoundError(scope_id)


class _Authenticator:
    enabled = False

    def __call__(self):
        return {}


def _client() -> AsyncClient:
    app = FastAPI()
    app.include_router(
        init_scope_router(_Scopes(), _Authenticator(), None, None), prefix="/scopes"
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://opal")


def _closed_port_url() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/missing"


@pytest.mark.asyncio
async def test_the_webhook_gets_the_scope_the_route_and_when_with_the_token(
    receiver, counted
):
    before = datetime.datetime.now(datetime.timezone.utc)
    async with _client() as client:
        response = await client.get("/scopes/ghost/policy")
        await _until(lambda: _outcomes(counted))
    after = datetime.datetime.now(datetime.timezone.utc)

    assert response.status_code == 404
    [post] = receiver.posts
    assert post["path"] == "/missing"
    assert post["authorization"] == f"Bearer {_TOKEN}"
    assert post["content_type"] == "application/json"
    body = post["body"]
    assert set(body) == {"scope_id", "route", "seen_at"}
    assert (body["scope_id"], body["route"]) == ("ghost", "policy")
    seen_at = datetime.datetime.fromisoformat(body["seen_at"])
    assert seen_at.utcoffset() == datetime.timedelta(0)
    assert before - datetime.timedelta(seconds=1) <= seen_at <= after
    assert _outcomes(counted) == ["sent"]


@pytest.mark.asyncio
async def test_once_per_scope_per_five_minutes(receiver, counted, clock):
    async with _client() as client:
        for route in ("policy", "data", "policy"):
            await client.get(f"/scopes/ghost/{route}")
        await client.get("/scopes/phantom/data")
        await _until(lambda: len(_outcomes(counted)) == 2)
        clock[0] += 299.0
        await client.get("/scopes/ghost/data")
        clock[0] += 1.0
        await client.get("/scopes/ghost/data")
        await _until(lambda: len(_outcomes(counted)) == 3)
        await asyncio.sleep(0.2)

    assert [(p["body"]["scope_id"], p["body"]["route"]) for p in receiver.posts] == [
        ("ghost", "policy"),
        ("phantom", "data"),
        ("ghost", "data"),
    ]
    assert _outcomes(counted) == ["sent"] * 3


@pytest.mark.asyncio
async def test_without_a_token_the_post_carries_no_authorization(
    receiver, counted, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", None)

    async with _client() as client:
        await client.get("/scopes/ghost/data")
        await _until(lambda: _outcomes(counted))

    assert receiver.posts[0]["authorization"] is None


@pytest.mark.asyncio
async def test_without_a_url_nothing_is_posted(counted):
    async with _client() as client:
        response = await client.get("/scopes/ghost/policy")
        await asyncio.sleep(0.2)

    assert response.status_code == 404
    assert _outcomes(counted) == []
    assert all("ghost" not in str(tags) for _, tags in counted)
    assert (
        "opal_server.scopes.missing_scope",
        {"route": "policy"},
    ) in counted


@pytest.mark.asyncio
async def test_a_down_endpoint_neither_delays_nor_fails_the_request(
    counted, monkeypatch
):
    url = _closed_port_url()
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", url)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", _TOKEN
    )

    with capture_logs() as logs:
        async with _client() as client:
            started = time.monotonic()
            response = await client.get("/scopes/ghost/policy")
            elapsed = time.monotonic() - started
            await _until(lambda: _outcomes(counted))

    assert response.status_code == 404
    assert elapsed < 1.0
    assert _outcomes(counted) == ["failed"]
    [warning] = [line for line in logs.text if "WARNING" in line and "webhook" in line]
    assert "ghost" in warning and url.removesuffix("/missing") in warning
    assert _TOKEN not in logs.combined


@pytest.mark.asyncio
async def test_a_slow_endpoint_neither_delays_nor_fails_the_request(
    receiver, counted, monkeypatch
):
    monkeypatch.setattr(missing_scope, "_WEBHOOK_TIMEOUT_SECONDS", 1.5)
    receiver.delay = 30.0

    with capture_logs() as logs:
        async with _client() as client:
            started = time.monotonic()
            policy = await client.get("/scopes/ghost/policy")
            data = await client.get("/scopes/phantom/data")
            elapsed = time.monotonic() - started
            await _until(lambda: len(receiver.posts) == 2)
            assert _outcomes(counted) == []
            await _until(lambda: len(_outcomes(counted)) == 2)

    assert (policy.status_code, data.status_code) == (404, 404)
    assert elapsed < 0.75, f"the requests took {elapsed:.2f}s"
    assert _outcomes(counted) == ["timeout", "timeout"]
    assert _TOKEN not in logs.combined


@pytest.mark.asyncio
async def test_an_endpoint_that_refuses_is_counted_and_logged(receiver, counted):
    receiver.status = 401

    with capture_logs() as logs:
        async with _client() as client:
            await client.get("/scopes/ghost/data")
            await _until(lambda: _outcomes(counted))

    assert _outcomes(counted) == ["rejected"]
    [warning] = [line for line in logs.text if "WARNING" in line and "webhook" in line]
    assert "401" in warning and "ghost" in warning
    assert _TOKEN not in logs.combined


@pytest.mark.asyncio
async def test_at_most_a_hundred_posts_at_once_and_a_shed_scope_is_posted_later(
    receiver, counted, monkeypatch
):
    monkeypatch.setattr(missing_scope, "_WEBHOOK_MAX_INFLIGHT", 1)
    receiver.delay = 0.5

    async with _client() as client:
        await client.get("/scopes/ghost/policy")
        await client.get("/scopes/phantom/policy")
        assert _outcomes(counted) == ["shed"]
        await _until(lambda: _outcomes(counted) == ["shed", "sent"])
        await client.get("/scopes/phantom/policy")
        await _until(lambda: _outcomes(counted) == ["shed", "sent", "sent"])

    assert [p["body"]["scope_id"] for p in receiver.posts] == ["ghost", "phantom"]


def test_the_cap_is_a_hundred():
    assert missing_scope._WEBHOOK_MAX_INFLIGHT == 100
    assert missing_scope._WEBHOOK_WINDOW_SECONDS == 300.0
    assert missing_scope._WEBHOOK_TIMEOUT_SECONDS == 5.0


@pytest.mark.asyncio
async def test_the_scopes_remembered_are_bounded(receiver, counted, monkeypatch, clock):
    """The oldest scope is forgotten first, and may then be posted again inside
    its window."""
    monkeypatch.setattr(missing_scope, "_WEBHOOK_TRACKED_MAX", 2)

    async with _client() as client:
        for scope_id in ("a", "b", "c", "a", "c"):
            clock[0] += 1.0
            await client.get(f"/scopes/{scope_id}/data")
        await _until(lambda: len(_outcomes(counted)) == 4)
        await asyncio.sleep(0.2)

    assert [p["body"]["scope_id"] for p in receiver.posts] == ["a", "b", "c", "a"]


_SECRET_PATH = "/hooks/path-secret-value"
_SECRET_QUERY = "?token=url-secret-value&key=other-secret-value"


def _secrets_logged(logs) -> List[str]:
    return [
        secret
        for secret in (
            _TOKEN,
            "path-secret-value",
            "url-secret-value",
            "other-secret-value",
            "/hooks",
        )
        if secret in logs.combined
    ]


@pytest.mark.parametrize(
    "outcome", ["sent", "rejected", "timeout", "failed"], ids=lambda o: o
)
@pytest.mark.asyncio
async def test_only_the_url_s_scheme_host_and_port_are_logged(
    receiver, counted, monkeypatch, outcome
):
    """A webhook URL often carries its secret in the path or the query."""
    origin = _closed_port_url().removesuffix("/missing")
    if outcome != "failed":
        origin = receiver.origin
    url = f"{origin}{_SECRET_PATH}{_SECRET_QUERY}"
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", url)
    monkeypatch.setattr(missing_scope, "_WEBHOOK_TIMEOUT_SECONDS", 0.5)
    receiver.status = 500 if outcome == "rejected" else 204
    receiver.delay = 5.0 if outcome == "timeout" else 0.0

    with capture_logs() as logs:
        async with _client() as client:
            await client.get("/scopes/ghost/data")
            await _until(lambda: _outcomes(counted))

    assert _outcomes(counted) == [outcome]
    if outcome != "failed":
        assert receiver.posts[0]["path"] == f"{_SECRET_PATH}{_SECRET_QUERY}"
    assert _secrets_logged(logs) == []
    assert len([line for line in logs.text if "ghost" in line and origin in line]) == 1


@pytest.mark.parametrize(
    "raised, outcome, level",
    [
        (RuntimeError, "error", "ERROR"),
        (aiohttp.ClientConnectionError, "failed", "WARNING"),
    ],
    ids=["fault-of-its-own", "client-error"],
)
@pytest.mark.asyncio
async def test_an_error_s_text_is_logged_without_the_token_or_the_url_s_secret(
    receiver, counted, monkeypatch, raised, outcome, level
):
    """An error the POST raises, whatever it says, is logged with the token and
    the URL's credentials masked.

    Not a failure of the POST (RuntimeError) is an ERROR rather than a
    task exception nobody reads; the request is answered either way.
    """
    url = f"{receiver.origin}{_SECRET_PATH}{_SECRET_QUERY}"
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", url)

    class _Broken:
        def __init__(self, *args, **kwargs):
            raise raised(f"could not post to {url} ({_SECRET_PATH}) with {_TOKEN}")

    monkeypatch.setattr(missing_scope.aiohttp, "ClientSession", _Broken)

    with capture_logs() as logs:
        async with _client() as client:
            response = await client.get("/scopes/ghost/policy")
            await _until(lambda: _outcomes(counted))

    assert response.status_code == 404
    assert _outcomes(counted) == [outcome]
    [line] = [line for line in logs.text if level in line and "webhook" in line]
    assert raised.__name__ in line and "ghost" in line
    assert receiver.origin in line
    assert _secrets_logged(logs) == []
