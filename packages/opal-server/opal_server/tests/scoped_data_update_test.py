"""POST /scopes/{scope_id}/data/update must namespace entry topics the
same way the scoped client filters them.

The client on scope ``documents`` with ``OPAL_DATA_TOPICS=data``
subscribes to ``documents:data:data`` and then skips any entry whose
topics are disjoint from that set. Prefixing only as ``data:{topic}``
and publishing through ScopedServerSideTopicPublisher leaves the
payload at ``data:data`` while the channel is ``documents:data:data``,
so every entry is dropped. Prefixing as ``{scope_id}:data:{topic}``
*and then* going through Scoped double-prefixes the channel. Both
halves have to be right at once.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.topics.publisher import ServerSideTopicPublisher
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())


class FakeAuthenticator:
    """Mimics a JWTAuthenticator whose verifier is disabled (no public key)."""

    enabled = False

    def __call__(self):
        return {}


class FakePubSubEndpoint:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((list(topics), data))


def _scope(scope_id="documents"):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url="https://git/repo.git",
            branch="main",
            auth=NoAuthData(auth_type="none"),
        ),
        data={"entries": []},
    )


def _client(repo, base_dir, pubsub):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=pubsub)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )
    return TestClient(app)


def test_scoped_data_update_entry_topics_match_the_scoped_client(
    tmp_path, monkeypatch
):
    """Channel and payload topics must both be ``{scope_id}:data:{topic}``.

    ServerSideTopicPublisher.publish fire-and-forgets via create_task;
    await the impl so the fake endpoint is populated before we assert.
    The Scoped publisher still wraps this, so a leftover Scoped path
    would still double-prefix the channel and fail the assertion.

    Mutation: ``data:{topic}`` (no scope) -> payload disjoint, skip.
    Mutation: prefix + Scoped publisher -> channel ``{scope}:{scope}:...``.
    """

    async def publish_now(self, topics, data=None):
        await self._publish_impl(topics, data)

    monkeypatch.setattr(ServerSideTopicPublisher, "publish", publish_now)

    scope_id = "documents"
    topic = "data"
    client_data_topics = {f"{scope_id}:data:{topic}"}
    pubsub = FakePubSubEndpoint()
    client = _client(FakeScopeRepository([_scope(scope_id)]), tmp_path, pubsub)

    resp = client.post(
        f"/scopes/{scope_id}/data/update",
        json={
            "entries": [
                {
                    "url": "http://opal_server:7002/healthcheck",
                    "topics": [topic],
                    "dst_path": "/scope_probe",
                    "save_method": "PUT",
                }
            ],
            "reason": "repro",
        },
    )

    assert resp.status_code == 200
    assert len(pubsub.published) == 1
    channel_topics, payload = pubsub.published[0]

    assert set(channel_topics) == client_data_topics, (
        f"channel {channel_topics!r} is not the scoped client subscription"
    )
    entry_topics = set(payload["entries"][0]["topics"])
    assert not entry_topics.isdisjoint(client_data_topics), (
        f"entry topics {entry_topics!r} would be skipped by the scoped client"
    )
