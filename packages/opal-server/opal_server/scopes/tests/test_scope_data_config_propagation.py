"""Regression tests for permitio/opal#779.

When an OPAL Agent in scopes mode requests its scope's data-source configuration
via ``GET /scopes/{scope_id}/data`` for a scope that is not present in the scope
repository at request time (the create -> sync race window), the server used to
fall back to the server-global ``OPAL_DATA_CONFIG_SOURCES`` (which carries the
default topic ``policy_data``) and serve it as an authoritative HTTP 200.

A scoped agent subscribes to a scope-prefixed data topic (e.g. ``documents:data:data``),
so an entry topic'd ``policy_data`` never matches; the agent discards it, loads no
base data, and all OPA authorization requests fail.

These tests pin BOTH branches of the route:

* ``test_absent_scope_does_not_serve_default_data_config`` (FAIL_TO_PASS):
  with the scope ABSENT, the endpoint must not leak the server default. The fix
  serves an empty, scope-shaped config instead. This FAILS at the unpatched
  baseline (default served) and FAILS again if the one-line fix is reverted
  (true negative control, not a tautology).
* ``test_present_scope_serves_its_own_data`` (PASS_TO_PASS / happy path):
  once the scope IS in the repository, the endpoint returns the scope's own data
  sources. This passes before and after the fix and guards against regressing the
  un-broken happy path.
* ``test_absent_scope_with_external_source_url_still_redirects``: the
  ``external_source_url`` redirect branch in the same not-found path is preserved
  (the fix only changed the else-branch).

Delivery to already-connected agents is pinned by the ``test_put_scope_*`` group:
``PUT /scopes`` must publish the scope's data-source entries as a data update whose
topics are namespaced ``{scope_id}:data:{topic}`` — the form a scoped agent both
subscribes to and content-filters entries by. Without that publish, an agent that
connected before the scope was created (or before its data config changed) is never
re-triggered and never receives the scope's data sources, even though policy
propagates (the reported symptom of issue #779).
"""

import asyncio
from typing import Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_websocket_pubsub import PubSubEndpoint
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTAlgorithm
from opal_common.authentication.verifier import JWTVerifier
from opal_common.schemas.data import (
    DataSourceConfig,
    DataSourceEntry,
    ServerDataSourceConfig,
)
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError

# --- The scope the operator configured via POST /scopes (issue #779 repro) ---
SCOPE_ID = "documents"
SCOPE_DATA_TOPIC = "data"  # agent subscribes to "<scope_id>:data:<topic>"
SCOPE_DATA_URL = "http://example.test/scoped-data"

# --- The server-level default (OPAL_DATA_CONFIG_SOURCES), topic "policy_data" ---
DEFAULT_DATA_URL = "http://example.test/policy-data"
DEFAULT_DATA_TOPIC = "policy_data"


class InMemoryScopeRepository:
    """Minimal in-memory stand-in for ScopeRepository (no Redis required).

    Mirrors the get/put/all/delete contract used by the scope router so
    the test exercises the real route logic, not a mock of it.
    """

    def __init__(self):
        self._scopes: Dict[str, Scope] = {}

    async def get(self, scope_id: str) -> Scope:
        if scope_id in self._scopes:
            return self._scopes[scope_id]
        raise ScopeNotFoundError(scope_id)

    async def put(self, scope: Scope):
        self._scopes[scope.scope_id] = scope

    async def all(self) -> List[Scope]:
        return list(self._scopes.values())

    async def delete(self, scope_id: str):
        self._scopes.pop(scope_id, None)


def _scope_with_data() -> Scope:
    """The scope the reporter configured: a git policy + a non-default data source."""
    return Scope(
        scope_id=SCOPE_ID,
        policy=GitPolicyScopeSource(
            source_type="git",
            url="https://example.test/policy.git",
            auth=NoAuthData(),
        ),
        data=DataSourceConfig(
            entries=[
                DataSourceEntry(
                    url=SCOPE_DATA_URL,
                    topics=[SCOPE_DATA_TOPIC],
                )
            ]
        ),
    )


def _disabled_authenticator() -> JWTAuthenticator:
    # public_key=None -> verifier.enabled == False -> auth is bypassed,
    # which is the OPAL "insecure"/dev default and irrelevant to this bug.
    verifier = JWTVerifier(
        public_key=None,
        algorithm=JWTAlgorithm.RS256,
        audience="https://api.opal.ac/v1/",
        issuer="https://opal.ac/",
    )
    return JWTAuthenticator(verifier)


def _build_client(scopes: InMemoryScopeRepository) -> TestClient:
    app = FastAPI()
    router = init_scope_router(
        scopes,
        _disabled_authenticator(),
        PubSubEndpoint(),
    )
    app.include_router(router, prefix="/scopes")
    return TestClient(app)


def _topics_in_response(payload) -> List[str]:
    topics: List[str] = []
    for entry in payload.get("entries", []):
        topics.extend(entry.get("topics", []))
    return topics


@pytest.fixture(autouse=True)
def _server_default_data_config():
    """Set OPAL_DATA_CONFIG_SOURCES to a non-default static config (topic
    policy_data).

    Restores the original after each test so other tests are unaffected.
    """
    original = opal_server_config.DATA_CONFIG_SOURCES
    opal_server_config.DATA_CONFIG_SOURCES = ServerDataSourceConfig(
        config=DataSourceConfig(
            entries=[
                DataSourceEntry(
                    url=DEFAULT_DATA_URL,
                    topics=[DEFAULT_DATA_TOPIC],
                )
            ]
        )
    )
    yield
    opal_server_config.DATA_CONFIG_SOURCES = original


def test_absent_scope_does_not_serve_default_data_config():
    """FAIL_TO_PASS: an absent scope must not be served the server-global default.

    Fails at the unpatched baseline (default `policy_data` config returned) and
    fails again on a one-line revert of the fix -> a true negative control.
    """
    scopes = InMemoryScopeRepository()  # scope ABSENT (create->sync race window)
    client = _build_client(scopes)

    response = client.get(f"/scopes/{SCOPE_ID}/data")

    assert response.status_code == 200, response.text
    payload = response.json()
    topics = _topics_in_response(payload)

    assert DEFAULT_DATA_TOPIC not in topics, (
        "issue #779: server returned the default OPAL_DATA_CONFIG_SOURCES "
        f"(topic '{DEFAULT_DATA_TOPIC}') for absent scope '{SCOPE_ID}'. A scoped "
        "agent subscribed to its scope topic receives no matching data and all OPA "
        f"authorization requests fail. Returned topics: {topics}"
    )
    # The only correct config for a not-yet-synced scope is an empty one — the
    # server has no scope-specific data to serve, and must not borrow another
    # scope's / the global default's topic.
    assert (
        payload.get("entries", []) == []
    ), f"absent scope must yield an empty data config, got: {payload}"


def test_present_scope_serves_its_own_data_with_namespaced_topics():
    """Happy path: a present scope is served its own data sources, with entry
    topics namespaced to the ``{scope_id}:data:{topic}`` form the scoped agent
    content-filters by (a bare authored topic like ``data`` would otherwise be
    silently discarded by the agent — the #779 symptom via the happy path)."""
    scopes = InMemoryScopeRepository()
    asyncio.run(scopes.put(_scope_with_data()))
    client = _build_client(scopes)

    response = client.get(f"/scopes/{SCOPE_ID}/data")

    assert response.status_code == 200, response.text
    payload = response.json()
    urls = [entry.get("url") for entry in payload.get("entries", [])]
    topics = _topics_in_response(payload)

    assert (
        SCOPE_DATA_URL in urls
    ), f"expected the scope's configured data source ({SCOPE_DATA_URL}); got: {payload}"
    assert f"{SCOPE_ID}:data:{SCOPE_DATA_TOPIC}" in topics, topics
    assert SCOPE_DATA_TOPIC not in topics  # bare form would be discarded
    assert DEFAULT_DATA_TOPIC not in topics


def test_present_scope_default_topic_entries_are_served_namespaced():
    """A data entry authored WITHOUT explicit topics gets the schema default
    (bare ``policy_data``), which a scoped agent always discards as topic-
    disjoint — the permanent (non-race) variant of the #779 symptom.

    The served config must namespace it to ``{scope_id}:data:policy_data``.
    """
    scope = _scope_with_data()
    scope.data = DataSourceConfig(entries=[DataSourceEntry(url=SCOPE_DATA_URL)])
    scopes = InMemoryScopeRepository()
    asyncio.run(scopes.put(scope))
    client = _build_client(scopes)

    response = client.get(f"/scopes/{SCOPE_ID}/data")

    assert response.status_code == 200, response.text
    topics = _topics_in_response(response.json())
    assert f"{SCOPE_ID}:data:{DEFAULT_DATA_TOPIC}" in topics, topics
    assert DEFAULT_DATA_TOPIC not in topics, (
        "bare default topic served to a scoped agent — it will be discarded "
        f"as topic-disjoint and the scope loads no data; got: {topics}"
    )


def test_present_scope_namespaced_authored_topics_served_unchanged():
    """Operator-authored already-namespaced topics (the reporter's style, e.g.
    ``documents:data:data``) must pass through serve-side normalization
    unchanged — no double prefix."""
    authored = f"{SCOPE_ID}:data:{SCOPE_DATA_TOPIC}"
    scope = _scope_with_data()
    scope.data = DataSourceConfig(
        entries=[DataSourceEntry(url=SCOPE_DATA_URL, topics=[authored])]
    )
    scopes = InMemoryScopeRepository()
    asyncio.run(scopes.put(scope))
    client = _build_client(scopes)

    response = client.get(f"/scopes/{SCOPE_ID}/data")

    assert response.status_code == 200, response.text
    assert _topics_in_response(response.json()) == [authored]


def test_absent_scope_with_external_source_url_still_redirects():
    """The external_source_url redirect branch of the not-found path is
    preserved.

    The fix only replaces the else-branch return; an
    OPAL_DATA_CONFIG_SOURCES that declares an external_source_url must
    still produce a redirect for an absent scope.
    """
    # ServerDataSourceConfig enforces exactly one of config / external_source_url.
    opal_server_config.DATA_CONFIG_SOURCES = ServerDataSourceConfig(
        external_source_url="http://external.test/data",
    )
    scopes = InMemoryScopeRepository()  # scope ABSENT
    client = _build_client(scopes)

    response = client.get(f"/scopes/{SCOPE_ID}/data", follow_redirects=False)

    assert response.status_code == 307, response.text
    assert response.headers["location"].startswith("http://external.test/data")


# ---------------------------------------------------------------------------
# PUT /scopes must notify connected scoped agents of the data configuration
# ---------------------------------------------------------------------------


class SpyPubSubEndpoint:
    """Duck-typed PubSubEndpoint stand-in that records every publish call.

    The scope router only calls ``endpoint.publish(topics, data)`` (directly
    for the sync-trigger webhook, and via ``ServerSideTopicPublisher`` for
    data updates), so recording publishes captures the route's full pub/sub
    behavior.
    """

    def __init__(self):
        self.publishes: List[tuple] = []
        self._published = asyncio.Event()

    async def publish(self, topics, data=None):
        self.publishes.append((list(topics), data))
        self._published.set()

    async def wait_for_publish_count(self, count: int, timeout: float = 5.0):
        """Wait until at least `count` publishes were recorded (publishes via
        ServerSideTopicPublisher run as fire-and-forget background tasks)."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while len(self.publishes) < count:
            self._published.clear()
            if len(self.publishes) >= count:
                break
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"expected >= {count} publishes within {timeout}s, "
                    f"got {len(self.publishes)}: {self.publishes}"
                )
            await asyncio.wait_for(self._published.wait(), remaining)

    def data_update_publishes(self) -> List[tuple]:
        """Publishes that carry a DataUpdate payload (entries), i.e. not the
        sync-trigger webhook message."""
        return [
            (topics, data)
            for topics, data in self.publishes
            if isinstance(data, dict) and "entries" in data
        ]


def _scope_put_body(topics: List[str]) -> dict:
    return {
        "scope_id": SCOPE_ID,
        "policy": {
            "source_type": "git",
            "url": "https://example.test/policy.git",
            "auth": {"auth_type": "none"},
        },
        "data": {
            "entries": [
                {"url": SCOPE_DATA_URL, "topics": topics, "dst_path": "/scoped"}
            ]
        },
    }


def test_put_scope_publishes_namespaced_data_update():
    """FAIL_TO_PASS (issue #779, delivery): creating/updating a scope must
    publish its data-source entries to the scope's data topics.

    A scoped agent subscribes to (and content-filters entries by)
    ``{scope_id}:data:{topic}``; it fetches /scopes/{scope_id}/data only
    on (re)connect. Without this publish, an agent that connected before
    the scope existed never receives the scope's data sources (while
    policy DOES propagate via the sync notification) — the reported
    symptom.
    """
    expected_topic = f"{SCOPE_ID}:data:{SCOPE_DATA_TOPIC}"
    scopes = InMemoryScopeRepository()
    app = FastAPI()
    spy = SpyPubSubEndpoint()
    router = init_scope_router(scopes, _disabled_authenticator(), spy)
    app.include_router(router, prefix="/scopes")

    with TestClient(app) as client:
        response = client.put(
            "/scopes", json=_scope_put_body(topics=[SCOPE_DATA_TOPIC])
        )
        assert response.status_code == 201, response.text
        # webhook sync-trigger + the data update = 2 publishes
        client.portal.call(spy.wait_for_publish_count, 2)

    updates = spy.data_update_publishes()
    assert updates, (
        "issue #779: PUT /scopes did not publish any data update — a scoped "
        "agent already connected to the server is never notified of the "
        f"scope's data sources. Recorded publishes: {spy.publishes}"
    )
    channel_topics, payload = updates[0]
    assert expected_topic in channel_topics, (
        "data update was not published on the scope-namespaced topic the "
        f"agent subscribes to ({expected_topic}); got: {channel_topics}"
    )
    entry_topics = [t for e in payload["entries"] for t in e["topics"]]
    assert expected_topic in entry_topics, (
        "published entry topics must be scope-namespaced or the agent's "
        f"content filter discards them; got: {entry_topics}"
    )
    urls = [e["url"] for e in payload["entries"]]
    assert urls == [SCOPE_DATA_URL]


def test_put_scope_does_not_double_namespace_topics():
    """Entries authored with already-namespaced topics (the documented agent
    subscription form, e.g. ``documents:data:data``) must pass through
    unchanged — not become ``documents:data:documents:data:data``."""
    authored = f"{SCOPE_ID}:data:{SCOPE_DATA_TOPIC}"
    scopes = InMemoryScopeRepository()
    app = FastAPI()
    spy = SpyPubSubEndpoint()
    app.include_router(
        init_scope_router(scopes, _disabled_authenticator(), spy), prefix="/scopes"
    )

    with TestClient(app) as client:
        response = client.put("/scopes", json=_scope_put_body(topics=[authored]))
        assert response.status_code == 201, response.text
        client.portal.call(spy.wait_for_publish_count, 2)

    updates = spy.data_update_publishes()
    assert updates
    channel_topics, payload = updates[0]
    entry_topics = [t for e in payload["entries"] for t in e["topics"]]
    assert entry_topics == [authored], entry_topics
    assert channel_topics == [authored], channel_topics


def test_put_scope_without_data_entries_publishes_no_data_update():
    """A scope with no data entries triggers only the sync webhook — no
    empty/spurious data update is broadcast."""
    scopes = InMemoryScopeRepository()
    app = FastAPI()
    spy = SpyPubSubEndpoint()
    app.include_router(
        init_scope_router(scopes, _disabled_authenticator(), spy), prefix="/scopes"
    )

    body = _scope_put_body(topics=[SCOPE_DATA_TOPIC])
    body["data"] = {"entries": []}

    with TestClient(app) as client:
        response = client.put("/scopes", json=body)
        assert response.status_code == 201, response.text
        client.portal.call(spy.wait_for_publish_count, 1)

    assert spy.data_update_publishes() == [], spy.publishes


def test_put_scope_persists_authored_topics_unmodified():
    """Namespacing happens on a copy for the publish only: the persisted scope
    (served verbatim by GET /scopes/{scope_id}/data on agent connect) keeps the
    operator-authored topic form."""
    scopes = InMemoryScopeRepository()
    app = FastAPI()
    spy = SpyPubSubEndpoint()
    app.include_router(
        init_scope_router(scopes, _disabled_authenticator(), spy), prefix="/scopes"
    )

    with TestClient(app) as client:
        response = client.put(
            "/scopes", json=_scope_put_body(topics=[SCOPE_DATA_TOPIC])
        )
        assert response.status_code == 201, response.text
        client.portal.call(spy.wait_for_publish_count, 2)

    stored = asyncio.run(scopes.get(SCOPE_ID))
    assert [t for e in stored.data.entries for t in e.topics] == [SCOPE_DATA_TOPIC]


def test_put_scope_republishes_only_on_data_config_change():
    """Idempotent re-PUTs must not re-broadcast (no client re-fetch storm) —
    mirroring the policy path, which notifies only on new commits.

    A re-PUT with a CHANGED data config must publish again.
    """
    scopes = InMemoryScopeRepository()
    app = FastAPI()
    spy = SpyPubSubEndpoint()
    app.include_router(
        init_scope_router(scopes, _disabled_authenticator(), spy), prefix="/scopes"
    )

    body = _scope_put_body(topics=[SCOPE_DATA_TOPIC])
    with TestClient(app) as client:
        assert client.put("/scopes", json=body).status_code == 201
        client.portal.call(spy.wait_for_publish_count, 2)
        assert len(spy.data_update_publishes()) == 1

        # identical re-PUT: webhook fires again, data update must NOT
        assert client.put("/scopes", json=body).status_code == 201
        client.portal.call(spy.wait_for_publish_count, 3)
        assert len(spy.data_update_publishes()) == 1, spy.publishes

        # changed data config: must publish again
        body["data"]["entries"][0]["dst_path"] = "/scoped-v2"
        assert client.put("/scopes", json=body).status_code == 201
        client.portal.call(spy.wait_for_publish_count, 5)
        assert len(spy.data_update_publishes()) == 2, spy.publishes
