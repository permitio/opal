"""The data update a PUT /scopes publishes, and the topics of a scope's data
entries.

A PUT that stores a scope whose data config is new or changed publishes the
scope's data entries, topics as ``{scope_id}:data:{topic}``, once the sync
of the scope has been requested; a PUT that fails before that publishes no
data update. POST /scopes/{scope_id}/data/update gives its entries the same
topics: a topic that already carries the scope's prefix keeps it once.
"""

import warnings

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.data import DataSourceConfig, DataSourceEntry
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.redaction_fixtures import capture_logs
from opal_common.topics.publisher import ServerSideTopicPublisher
from opal_server.config import opal_server_config
from opal_server.scopes.api import init_scope_router, normalize_data_topics_for_scope
from opal_server.scopes.scope_repository import ScopeNotFoundError

pytestmark = pytest.mark.fetch_backend("cli")

_URL = "http://data.example.test/scoped"


class _Scopes:
    def __init__(self, scopes=()):
        self.scopes = {s.scope_id: s for s in scopes}
        self.unreadable = set()
        self.put_fails = False
        self.put_stores_then_fails = False

    async def get(self, scope_id):
        if scope_id in self.unreadable:
            raise ValueError("the stored record does not parse")
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]

    async def put(self, scope):
        if self.put_fails:
            raise ConnectionError("the scope store is down")
        self.scopes[scope.scope_id] = scope
        if self.put_stores_then_fails:
            raise ConnectionError("the scope store went away after the write")


class _Endpoint:
    def __init__(self):
        self.published = []
        self.sync_request_fails = False

    async def publish(self, topics, data=None):
        if (
            topics == opal_server_config.POLICY_REPO_WEBHOOK_TOPIC
            and self.sync_request_fails
        ):
            raise ConnectionError("the broadcaster is down")
        self.published.append((topics, data))

    def data_updates(self):
        return [
            (topics, data)
            for topics, data in self.published
            if isinstance(data, dict) and "entries" in data
        ]


class _Authenticator:
    enabled = False

    def __call__(self):
        return {}


@pytest.fixture(autouse=True)
def _publish_in_the_request(monkeypatch, tmp_path):
    """ServerSideTopicPublisher publishes in a task of its own; run it inside
    the request, so that a test that asserts nothing was published does not
    pass because the task has not run yet."""

    async def publish_now(self, topics, data=None):
        await self._publish_impl(topics, data)

    monkeypatch.setattr(ServerSideTopicPublisher, "publish", publish_now)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))


def _scope(url="https://git.example.test/policy.git", topics=("data",)):
    return Scope(
        scope_id="documents",
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch="main", auth=NoAuthData()
        ),
        data=DataSourceConfig(
            entries=[
                {
                    "url": _URL,
                    "topics": list(topics),
                    "dst_path": "/scoped",
                    "config": {"headers": {"Authorization": "Bearer abc"}},
                    "periodic_update_interval": 30,
                }
            ]
        ),
    )


def _client(scopes, endpoint):
    app = FastAPI()
    app.include_router(
        init_scope_router(scopes, _Authenticator(), endpoint, None), prefix="/scopes"
    )
    return TestClient(app, raise_server_exceptions=False)


def _put(client, scope):
    return client.put("/scopes", json=scope.model_dump(mode="json"))


def test_the_data_update_keeps_every_field_of_the_entry_but_its_topics():
    """The client fetches each entry with its own config (its headers), into
    its dst_path."""
    endpoint = _Endpoint()

    assert _put(_client(_Scopes(), endpoint), _scope()).status_code == 201

    [(topics, update)] = endpoint.data_updates()
    assert topics == ["documents:data:data"]
    [entry] = update["entries"]
    assert entry["url"] == _URL
    assert entry["dst_path"] == "/scoped"
    assert entry["config"] == {"headers": {"Authorization": "Bearer abc"}}
    assert entry["periodic_update_interval"] == 30
    assert entry["topics"] == ["documents:data:data"]


def _data_warnings(logs):
    return [
        line
        for line in logs.text
        if "WARNING" in line and "data update of scope documents" in line
    ]


def test_a_put_whose_store_write_fails_publishes_no_data_update_and_says_so():
    scopes = _Scopes()
    scopes.put_fails = True
    endpoint = _Endpoint()

    with capture_logs() as logs:
        assert _put(_client(scopes, endpoint), _scope()).status_code == 500

    assert endpoint.data_updates() == []
    [warning] = _data_warnings(logs)
    assert "a retry will not publish it" in warning


def test_a_put_stored_before_its_store_failed_is_not_published_by_its_retry():
    """The store kept the record but answered an error: the retry finds the data
    stored and publishes nothing, so the failed request's WARNING is what says
    the clients get the entries only at their next connect."""
    scopes = _Scopes()
    scopes.put_stores_then_fails = True
    endpoint = _Endpoint()
    client = _client(scopes, endpoint)

    with capture_logs() as logs:
        assert _put(client, _scope()).status_code == 500
        scopes.put_stores_then_fails = False
        assert _put(client, _scope()).status_code == 201

    assert endpoint.data_updates() == []
    assert len(_data_warnings(logs)) == 1


def test_a_put_whose_sync_request_fails_still_publishes_the_data_update():
    """The data update goes out before the sync request.

    The record is stored by then, so a retry, which finds the data
    stored, would not send it.
    """
    endpoint = _Endpoint()
    endpoint.sync_request_fails = True
    scopes = _Scopes()
    client = _client(scopes, endpoint)

    with capture_logs() as logs:
        assert _put(client, _scope()).status_code == 500
        endpoint.sync_request_fails = False
        assert _put(client, _scope()).status_code == 201

    assert len(endpoint.data_updates()) == 1
    assert _data_warnings(logs) == []


def test_a_put_over_an_unreadable_record_publishes_the_data_update():
    """The previous data config cannot be read, so it is taken as changed."""
    scopes = _Scopes([_scope()])
    scopes.unreadable.add("documents")
    endpoint = _Endpoint()

    assert _put(_client(scopes, endpoint), _scope()).status_code == 201

    assert len(endpoint.data_updates()) == 1


def test_a_put_that_changes_only_the_policy_publishes_no_data_update():
    scopes = _Scopes([_scope()])
    endpoint = _Endpoint()

    response = _put(
        _client(scopes, endpoint), _scope(url="https://git.example.test/other.git")
    )

    assert response.status_code == 201
    assert endpoint.data_updates() == []
    syncs = [
        data
        for topics, data in endpoint.published
        if topics == opal_server_config.POLICY_REPO_WEBHOOK_TOPIC
    ]
    assert syncs == [{"scope_id": "documents", "force_fetch": True, "repointed": True}]


def test_a_put_that_changes_the_data_publishes_the_new_entries():
    scopes = _Scopes([_scope()])
    endpoint = _Endpoint()

    assert _put(_client(scopes, endpoint), _scope(topics=("users",))).status_code == 201

    [(topics, update)] = endpoint.data_updates()
    assert topics == ["documents:data:users"]
    assert update["entries"][0]["topics"] == ["documents:data:users"]


@pytest.mark.parametrize(
    "sent, published",
    [
        ("data", "documents:data:data"),
        ("documents:data:data", "documents:data:data"),
        ("other:data:data", "documents:data:other:data:data"),
    ],
    ids=["plain", "this-scope's-prefix", "another-scope's-prefix"],
)
def test_a_scoped_data_update_prefixes_each_topic_once(sent, published):
    """A topic already in this scope's form is kept; any other gets this
    scope's prefix, so an update sent for one scope never reaches another
    scope's clients."""
    endpoint = _Endpoint()
    client = _client(_Scopes([_scope()]), endpoint)

    response = client.post(
        "/scopes/documents/data/update",
        json={"entries": [{"url": _URL, "topics": [sent]}], "reason": "test"},
    )

    assert response.status_code == 200
    [(topics, update)] = endpoint.data_updates()
    assert topics == [published]
    assert update["entries"][0]["topics"] == [published]


def test_normalizing_a_scope_s_topics_warns_nothing():
    config = DataSourceConfig(entries=[DataSourceEntry(url=_URL, topics=["data"])])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        normalized = normalize_data_topics_for_scope("documents", config)

    assert normalized.entries[0].topics == ["documents:data:data"]
    assert config.entries[0].topics == ["data"]
