"""A scope's bundle request survives the window in which a pod has not fetched
the scope's branch yet, and a repoint always tells the scope's clients.

Right after PUT /scopes moves a scope to another repository, every pod's clone
of that repository lacks the scope's branch until its own fetch lands. Before
this, GET /scopes/:scope_id/policy answered those requests with a 409 "not
retryable". A client that already has a policy keeps it; one that starts in
that window makes five attempts and then waits, with no policy at all, for the
next policy message, which a pod whose fetch failed or that missed the PUT's
broadcast never sends. Now the route asks for a refresh of the scope and holds
the request in the clone wait. A branch that really does not exist still gets
its 409: within SCOPES_POLICY_BRANCH_REFRESH_INTERVAL straight away, and after
the hold otherwise.

The other half: a sync triggered by a repoint notifies the scope's clients even
when the clone's scope ref already equals the branch head, which is what a move
back to a repository the scope used before looks like.
"""
import datetime
from collections import OrderedDict
from pathlib import Path

import git
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.monitoring import metrics
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import BranchHeadNotFoundError, GitPolicyFetcher
from opal_server.scopes import api as scopes_api
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import NewCommitsCallbacks, ScopesService
from opal_server.scopes.task import ScopesPolicyWatcherTask

_WAIT_METRIC = "opal_server.scopes.policy_clone_wait"
_REFRESH_METRIC = "opal_server.scopes.policy_branch_refresh"
AUTHOR = git.Actor("test", "test@example.com")


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())

    async def put(self, scope):
        self._scopes[scope.scope_id] = scope


class FakeAuthenticator:
    enabled = False

    def __call__(self):
        return {}


class RecordingPubSub:
    def __init__(self, fail=False):
        self.published = []
        self._fail = fail

    async def publish(self, topics, data=None):
        if self._fail:
            raise ConnectionError("broadcaster down")
        self.published.append((topics, data))

    def refreshes(self):
        return [
            d
            for t, d in self.published
            if t == opal_server_config.POLICY_REPO_WEBHOOK_TOPIC
        ]


def _scope(scope_id="live", url="https://git/live.git", branch="main"):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=url,
            branch=branch,
            auth=NoAuthData(auth_type="none"),
        ),
        data={"entries": []},
    )


def _client(pubsub, *scopes):
    repo = FakeScopeRepository(list(scopes) or [_scope()])
    service = ScopesService(
        base_dir=Path("/unused"), scopes=repo, pubsub_endpoint=pubsub
    )
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )
    return TestClient(app)


def _missing():
    raise BranchHeadNotFoundError("Could not find current branch head")


def _ready():
    return PolicyBundle(manifest=[], hash="head", data_modules=[], policy_modules=[])


@pytest.fixture(autouse=True)
def bed(tmp_path, monkeypatch):
    """Wait and poll tuned to test timescales; per-process state reset."""
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", 60.0
    )
    monkeypatch.setattr(scopes_api, "_CLONE_WAIT_POLL_SECONDS", 0.02)
    monkeypatch.setattr(scopes_api, "_clone_wait_inflight", 0)
    monkeypatch.setattr(scopes_api, "_branch_refresh_requested", OrderedDict())
    yield
    assert scopes_api._clone_wait_inflight == 0, "a wait slot leaked"


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics, "increment", lambda metric, tags=None: calls.append((metric, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda *a, **k: None)
    monkeypatch.setattr(metrics, "event", lambda *a, **k: None)
    return calls


def _script(monkeypatch, *outcomes):
    """make_bundle plays ``outcomes`` in order, the last one repeating."""
    calls = []

    def fake(self, base_hash=None):
        calls.append(base_hash)
        return outcomes[min(len(calls) - 1, len(outcomes) - 1)]()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
    return calls


# --- the bundle route ----------------------------------------------------


def test_a_branch_fetched_while_held_is_served(monkeypatch, emitted):
    """The window this exists for: the pod's clone lacks the branch, the
    refresh the route asked for brings it, and the client gets its bundle.

    Mutation: answering BranchHeadNotFoundError straight away (as before)
    returns 409 and fails here."""
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing, _missing, _ready)

    resp = _client(pubsub).get("/scopes/live/policy?base_hash=abc")

    assert resp.status_code == 200, resp.text
    assert resp.json()["hash"] == "head"
    assert calls == ["abc", "abc", "abc"], "the client's base_hash was not kept"
    assert pubsub.refreshes() == [{"scope_id": "live", "force_fetch": True}]
    assert (_REFRESH_METRIC, None) in emitted
    assert (_WAIT_METRIC, {"outcome": "served", "for": "branch"}) in emitted


def test_a_branch_that_never_arrives_gets_the_409_after_the_hold(monkeypatch, emitted):
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing)

    resp = _client(pubsub).get("/scopes/live/policy")

    assert resp.status_code == 409
    assert "retry-after" not in {k.lower() for k in resp.headers}
    assert len(calls) > 1, "the route never re-checked while holding"
    assert len(pubsub.refreshes()) == 1
    assert (_WAIT_METRIC, {"outcome": "timeout", "for": "branch"}) in emitted


def test_within_the_interval_a_miss_is_answered_at_once(monkeypatch, emitted):
    """A branch that really does not exist must not hold every request: after
    one refresh, further misses of that scope on this worker get the old,
    immediate 409 until the interval is over.

    Mutation: dropping the claim check holds the second request and publishes a
    second refresh."""
    pubsub = RecordingPubSub()
    client = _client(pubsub)
    _script(monkeypatch, _missing)
    assert client.get("/scopes/live/policy").status_code == 409

    calls = _script(monkeypatch, _missing)
    resp = client.get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(calls) == 1, "the second miss was held"
    assert len(pubsub.refreshes()) == 1, "a second refresh was published"


def test_the_interval_is_per_scope(monkeypatch):
    pubsub = RecordingPubSub()
    client = _client(pubsub, _scope("one"), _scope("two"))
    _script(monkeypatch, _missing, _ready)
    assert client.get("/scopes/one/policy").status_code == 200
    _script(monkeypatch, _missing, _ready)
    assert client.get("/scopes/two/policy").status_code == 200
    assert [d["scope_id"] for d in pubsub.refreshes()] == ["one", "two"]


def test_a_new_interval_refreshes_again(monkeypatch):
    pubsub = RecordingPubSub()
    client = _client(pubsub)
    _script(monkeypatch, _missing)
    client.get("/scopes/live/policy")
    # The claim is older than the interval.
    scopes_api._branch_refresh_requested["live"] -= 61.0
    _script(monkeypatch, _missing, _ready)

    assert client.get("/scopes/live/policy").status_code == 200
    assert len(pubsub.refreshes()) == 2


@pytest.mark.parametrize("interval", [0.0, -1.0, float("nan"), float("-inf")])
def test_a_disabled_interval_keeps_the_immediate_409(monkeypatch, interval):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", interval
    )
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing, _ready)

    resp = _client(pubsub).get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(calls) == 1
    assert not pubsub.refreshes()


def test_no_clone_wait_means_no_branch_wait_either(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0)
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing, _ready)

    assert _client(pubsub).get("/scopes/live/policy").status_code == 409
    assert len(calls) == 1
    assert not pubsub.refreshes()


def test_a_refresh_that_cannot_be_published_is_not_waited_for(monkeypatch):
    """Holding the request would wait for a fetch nobody asked for."""
    calls = _script(monkeypatch, _missing, _ready)

    resp = _client(RecordingPubSub(fail=True)).get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(calls) == 1


def test_the_branch_wait_shares_the_clone_waits_cap(monkeypatch, emitted):
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 1)
    monkeypatch.setattr(scopes_api, "_clone_wait_inflight", 1)
    calls = _script(monkeypatch, _missing, _ready)

    resp = _client(RecordingPubSub()).get("/scopes/live/policy")
    # Released by hand: the fixture checks nothing else leaked.
    scopes_api._clone_wait_inflight = 0

    assert resp.status_code == 409, "a shed branch wait must answer as before"
    assert len(calls) == 1
    assert (_WAIT_METRIC, {"outcome": "shed", "for": "branch"}) in emitted


def test_the_claims_are_bounded(monkeypatch):
    monkeypatch.setattr(scopes_api, "_BRANCH_REFRESH_TRACKED_MAX", 3)
    for n in range(5):
        assert scopes_api._claim_branch_refresh(f"s{n}", float(n))
    assert list(scopes_api._branch_refresh_requested) == ["s2", "s3", "s4"]


# --- a repoint always notifies -------------------------------------------


def _put(client, scope):
    return client.put("/scopes", json=scope.model_dump())


def test_put_marks_a_changed_source_as_a_repoint(monkeypatch):
    monkeypatch.setattr(scopes_api, "verify_private_key_or_throw", lambda s: None)
    pubsub = RecordingPubSub()
    client = _client(pubsub, _scope(url="https://git/a.git"))

    assert _put(client, _scope(url="https://git/b.git")).status_code == 201
    assert _put(client, _scope(url="https://git/b.git")).status_code == 201
    assert _put(client, _scope("new", url="https://git/b.git")).status_code == 201

    assert [d["repointed"] for d in pubsub.refreshes()] == [True, False, False]


@pytest.mark.asyncio
async def test_the_trigger_passes_the_repoint_on():
    seen = []

    class Service:
        async def sync_scope(self, **kwargs):
            seen.append(kwargs)
            return None

    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    task._service = Service()
    await task.trigger(None, {"scope_id": "s", "force_fetch": True, "repointed": True})
    # A payload from a server without this change carries no flag.
    await task.trigger(None, {"scope_id": "s", "force_fetch": True})

    assert [k["notify_all"] for k in seen] == [True, False]
    assert all(isinstance(k["req_time"], datetime.datetime) for k in seen)


def _commit(repo, relpath, contents):
    path = Path(repo.working_tree_dir) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    repo.index.add([relpath])
    return repo.index.commit(f"update {relpath}", author=AUTHOR, committer=AUTHOR)


@pytest.mark.asyncio
@pytest.mark.parametrize("notify_all, published", [(False, 0), (True, 1)])
async def test_an_unmoved_head_notifies_only_on_a_repoint(
    tmp_path, notify_all, published
):
    """A move back to a repository whose clone still holds the scope's ref at
    the branch head: without the repoint flag no client is told, so one that
    fetched while the scope pointed elsewhere keeps that policy.

    Mutation: dropping `and not self._notify_all` from the early return makes
    the True case publish nothing."""
    source = GitPolicyScopeSource(
        source_type="git", url="https://git/a.git", auth=NoAuthData()
    )
    repo = git.Repo.init(GitPolicyFetcher.repo_clone_path(tmp_path, source))
    head = _commit(repo, "policy/a.rego", "package a\n").hexsha
    pubsub = RecordingPubSub()
    callbacks = NewCommitsCallbacks(
        tmp_path, "s", source, pubsub, notify_all=notify_all
    )

    await callbacks.on_update(head, head)

    assert len(pubsub.published) == published
    if published:
        topics, _ = pubsub.published[0]
        assert topics and all(t.startswith("s:") for t in topics)
