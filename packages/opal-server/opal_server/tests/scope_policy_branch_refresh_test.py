"""A scope's bundle request survives the window in which a pod has not fetched
the scope's branch yet, and a repoint always tells the scope's clients.

Right after PUT /scopes moves a scope to another repository, every pod's clone
of that repository lacks the scope's branch until its own fetch lands. Before
this, GET /scopes/:scope_id/policy answered those requests with a 409 "not
retryable". A client that already has a policy keeps it; one that starts in
that window makes five attempts and then waits, with no policy at all, for the
next policy message, which a pod whose fetch failed or that missed the PUT's
broadcast never sends. Now the route requests a sync of the scope and holds the
request in the clone wait, and every miss of that scope on the worker while the
sync is in flight is held with it. A branch that really does not exist still
gets its 409: at once once a requested sync has had its chance, and after the
hold otherwise.

The other half: a sync triggered by a repoint fetches and then notifies the
scope's clients even when the clone's scope ref already equals the branch
head, which is what a move back to a repository the scope used before looks
like.
"""
import asyncio
import datetime
from collections import OrderedDict
from pathlib import Path

import git
import httpx
import pygit2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.monitoring import metrics
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.log_capture import capture_records
from opal_server import git_fetcher as git_fetcher_module
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    BranchHeadNotFoundError,
    CloneNotPopulatedError,
    GitPolicyFetcher,
)
from opal_server.scopes import api as scopes_api
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import NewCommitsCallbacks, ScopesService
from opal_server.scopes.task import ScopesPolicyWatcherTask
from starlette.requests import Request

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
        self.fail = fail

    async def publish(self, topics, data=None):
        if self.fail:
            raise ConnectionError("broadcaster down")
        self.published.append((topics, data))

    def syncs(self):
        return [
            d
            for t, d in self.published
            if t == opal_server_config.POLICY_REPO_WEBHOOK_TOPIC
        ]


class SlowPubSub(RecordingPubSub):
    """A publish that suspends, as a real broadcaster's does: other requests
    run between a request's claim and the end of its publish."""

    def __init__(self, delay=0.05, fail=False):
        super().__init__(fail=False)
        self.delay = delay
        self.fail_after_delay = fail

    async def publish(self, topics, data=None):
        await asyncio.sleep(self.delay)
        if self.fail_after_delay:
            raise ConnectionError("broadcaster down")
        self.published.append((topics, data))


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


def _app(pubsub, *scopes):
    repo = FakeScopeRepository(list(scopes) or [_scope()])
    service = ScopesService(
        base_dir=Path("/unused"), scopes=repo, pubsub_endpoint=pubsub
    )
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )
    return app


def _client(pubsub, *scopes):
    return TestClient(_app(pubsub, *scopes))


def _missing():
    raise BranchHeadNotFoundError("Could not find current branch head")


def _populating():
    raise CloneNotPopulatedError("No refs/remotes/origin/* yet")


def _ready():
    return PolicyBundle(manifest=[], hash="head", data_modules=[], policy_modules=[])


WAIT = 0.3


@pytest.fixture(autouse=True)
def bed(tmp_path, monkeypatch):
    """Wait and poll tuned to test timescales; per-process state reset."""
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", WAIT)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", 60.0
    )
    monkeypatch.setattr(scopes_api, "_CLONE_WAIT_POLL_SECONDS", 0.02)
    monkeypatch.setattr(scopes_api, "_clone_wait_inflight", 0)
    monkeypatch.setattr(scopes_api, "_branch_refresh_requested", OrderedDict())
    monkeypatch.setattr(scopes_api, "_branch_refresh_publishes", set())
    yield
    assert scopes_api._clone_wait_inflight == 0, "a wait slot leaked"
    assert not scopes_api._branch_refresh_publishes, "a publish was left running"


@pytest.fixture
def emitted(monkeypatch):
    calls = {"increment": [], "event": []}
    monkeypatch.setattr(
        metrics,
        "increment",
        lambda metric, tags=None: calls["increment"].append((metric, tags)),
    )
    monkeypatch.setattr(
        metrics,
        "event",
        lambda title, message, tags=None: calls["event"].append((title, tags)),
    )
    monkeypatch.setattr(metrics, "gauge", lambda *a, **k: None)
    return calls


def _waits(emitted):
    return [tags for metric, tags in emitted["increment"] if metric == _WAIT_METRIC]


def _refreshes(emitted):
    return [
        (tags or {}).get("outcome")
        for metric, tags in emitted["increment"]
        if metric == _REFRESH_METRIC
    ]


def _script(monkeypatch, *outcomes):
    """make_bundle plays ``outcomes`` in order, the last one repeating.

    The branch wait's one-ref probe defers to it: every poll builds.
    What a poll costs on a real clone is
    test_a_held_poll_is_one_ref_lookup's.
    """
    calls = []

    def fake(self, base_hash=None):
        calls.append(base_hash)
        return outcomes[min(len(calls) - 1, len(outcomes) - 1)]()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
    monkeypatch.setattr(GitPolicyFetcher, "has_branch_ref", lambda self: True)
    return calls


def _gate(monkeypatch):
    """make_bundle reports a missing branch until the gate opens: keyed on the
    clone's state, so concurrent requests all see the same thing."""
    gate = {"open": False, "calls": 0}

    def fake(self, base_hash=None):
        gate["calls"] += 1
        if not gate["open"]:
            _missing()
        return _ready()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
    monkeypatch.setattr(GitPolicyFetcher, "has_branch_ref", lambda self: True)
    return gate


# --- the bundle route ----------------------------------------------------


def test_a_branch_fetched_while_held_is_served(monkeypatch, emitted):
    """The window this exists for: the pod's clone lacks the branch, the sync
    the route requested brings it, and the client gets its bundle.

    Mutation: answering BranchHeadNotFoundError straight away (as before)
    returns 409 and fails here."""
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing, _missing, _ready)

    resp = _client(pubsub).get("/scopes/live/policy?base_hash=abc")

    assert resp.status_code == 200, resp.text
    assert resp.json()["hash"] == "head"
    assert calls == ["abc", "abc", "abc"], "the client's base_hash was not kept"
    # Not forced: only servers whose clone lacks the branch fetch.
    assert pubsub.syncs() == [
        {"scope_id": "live", "force_fetch": False, "honor_backoff": True}
    ]
    assert _refreshes(emitted) == ["requested"]
    assert _waits(emitted) == [{"outcome": "served", "for": "branch"}]


def test_a_branch_that_never_arrives_gets_the_409_after_the_hold(monkeypatch, emitted):
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing)

    resp = _client(pubsub).get("/scopes/live/policy")

    assert resp.status_code == 409
    assert "retry-after" not in {k.lower() for k in resp.headers}
    assert len(calls) > 1, "the route never re-checked while holding"
    assert len(pubsub.syncs()) == 1
    assert _waits(emitted) == [{"outcome": "timeout", "for": "branch"}]


@pytest.mark.asyncio
async def test_concurrent_misses_ride_the_first_requests_sync(monkeypatch, emitted):
    """Several clients start on the scope at once (replicas of one PDP, or many
    PDPs right after a repoint). Every one of them is held and served, and only
    the first asks for the sync.

    Mutation: answering the immediate 409 to a miss while the first request's
    sync is in flight (the claim-only throttle) fails all but one request;
    recording the claim after the publish instead of before it requests one
    sync per request. The publish suspends, so the other misses arrive while
    the first request is still publishing.
    """
    pubsub = SlowPubSub()
    gate = _gate(monkeypatch)
    transport = httpx.ASGITransport(app=_app(pubsub))
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:

        async def open_soon():
            # Opens once every request has missed at least once.
            while gate["calls"] < 5:
                await asyncio.sleep(0.01)
            gate["open"] = True

        results = await asyncio.gather(
            *(client.get("/scopes/live/policy") for _ in range(5)), open_soon()
        )

    assert [r.status_code for r in results[:5]] == [200] * 5
    assert len(pubsub.syncs()) == 1, "a concurrent miss requested a second sync"
    assert [w["outcome"] for w in _waits(emitted)] == ["served"] * 5


def test_after_a_requested_sync_has_had_its_chance_a_miss_is_answered_at_once(
    monkeypatch,
):
    """A branch that really does not exist must not hold every request: once
    the hold of the first request has run out, misses within the interval get
    the old, immediate 409."""
    pubsub = RecordingPubSub()
    client = _client(pubsub)
    _script(monkeypatch, _missing)
    assert client.get("/scopes/live/policy").status_code == 409

    calls = _script(monkeypatch, _missing)
    resp = client.get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(calls) == 1, "the second miss was held"
    assert len(pubsub.syncs()) == 1, "a second sync was requested"


def test_a_new_interval_requests_again(monkeypatch):
    """An interval shorter than the hold: by the time the first hold runs out
    the interval is over, so the next miss requests a sync of its own."""
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", WAIT / 3
    )
    pubsub = RecordingPubSub()
    client = _client(pubsub)
    _script(monkeypatch, _missing)
    assert client.get("/scopes/live/policy").status_code == 409
    _script(monkeypatch, _missing, _ready)

    assert client.get("/scopes/live/policy").status_code == 200
    assert len(pubsub.syncs()) == 2


def test_the_interval_is_per_scope(monkeypatch):
    pubsub = RecordingPubSub()
    client = _client(pubsub, _scope("one"), _scope("two"))
    _script(monkeypatch, _missing, _ready)
    assert client.get("/scopes/one/policy").status_code == 200
    _script(monkeypatch, _missing, _ready)
    assert client.get("/scopes/two/policy").status_code == 200
    assert [d["scope_id"] for d in pubsub.syncs()] == ["one", "two"]


@pytest.mark.parametrize("interval", [0.0, -1.0, float("nan"), float("inf")])
def test_a_disabled_interval_keeps_the_immediate_409(monkeypatch, interval):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", interval
    )
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing, _ready)

    resp = _client(pubsub).get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(calls) == 1
    assert not pubsub.syncs()


def test_no_clone_wait_means_no_branch_wait_either(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0)
    pubsub = RecordingPubSub()
    calls = _script(monkeypatch, _missing, _ready)

    assert _client(pubsub).get("/scopes/live/policy").status_code == 409
    assert len(calls) == 1
    assert not pubsub.syncs()


def test_a_sync_that_cannot_be_requested_gives_the_interval_back(monkeypatch, emitted):
    """Holding would wait for a fetch nobody asked for, so the request gets the
    409; and the claim is dropped, so the next miss asks again instead of
    getting the immediate 409 for the rest of the interval.

    Mutation: keeping the claim on a failed publish makes the second request
    ride a sync nobody requested: it is answered without any sync being
    published.
    """
    pubsub = RecordingPubSub(fail=True)
    client = _client(pubsub)
    calls = _script(monkeypatch, _missing, _ready)
    assert client.get("/scopes/live/policy").status_code == 409
    assert len(calls) == 1

    pubsub.fail = False
    _script(monkeypatch, _missing, _ready)
    assert client.get("/scopes/live/policy").status_code == 200
    assert len(pubsub.syncs()) == 1
    assert _refreshes(emitted) == ["publish_failed", "requested"]


def test_a_shed_request_neither_requests_a_sync_nor_uses_up_the_interval(
    monkeypatch, emitted
):
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 1)
    pubsub = RecordingPubSub()
    client = _client(pubsub)
    calls = _script(monkeypatch, _missing, _ready)
    monkeypatch.setattr(scopes_api, "_clone_wait_inflight", 1)
    try:
        resp = client.get("/scopes/live/policy")
    finally:
        # The slot is held by "another request"; give it back either way so
        # the fixture's leak check points at a real leak.
        scopes_api._clone_wait_inflight = 0

    assert resp.status_code == 409, "a shed branch wait must answer as before"
    assert len(calls) == 1
    assert not pubsub.syncs(), "a shed request requested a sync"
    assert _waits(emitted) == [{"outcome": "shed", "for": "branch"}]

    _script(monkeypatch, _missing, _ready)
    assert client.get("/scopes/live/policy").status_code == 200
    assert len(pubsub.syncs()) == 1


def test_a_clone_that_lands_without_the_branch_is_waited_for(monkeypatch, emitted):
    """The in-loop arm: the clone was still being populated, then lands
    without the scope's branch. The request asks for the sync once and keeps
    holding."""
    pubsub = RecordingPubSub()
    _script(monkeypatch, _populating, _missing, _missing, _ready)

    resp = _client(pubsub).get("/scopes/live/policy")

    assert resp.status_code == 200
    assert pubsub.syncs() == [
        {"scope_id": "live", "force_fetch": False, "honor_backoff": True}
    ]
    assert _waits(emitted) == [{"outcome": "served", "for": "branch"}]


def test_a_clone_that_lands_without_the_branch_for_good_gets_the_409(
    monkeypatch, emitted
):
    pubsub = RecordingPubSub()
    _script(monkeypatch, _populating, _missing)

    resp = _client(pubsub).get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(pubsub.syncs()) == 1
    assert _waits(emitted) == [{"outcome": "timeout", "for": "branch"}]


def test_a_plain_clone_wait_is_tagged_as_one(monkeypatch, emitted):
    _script(monkeypatch, _populating, _ready)

    assert _client(RecordingPubSub()).get("/scopes/live/policy").status_code == 200
    assert _waits(emitted) == [{"outcome": "served", "for": "clone"}]


@pytest.mark.asyncio
async def test_a_client_that_hangs_up_during_a_branch_wait_is_not_reported(
    monkeypatch, emitted
):
    """The 409 is shaped for a socket nobody is reading: no ERROR line and no
    unavailable event for it, as on the clone wait's 503."""
    polls = {"n": 0}

    async def hung_up_after_two_polls(self):
        polls["n"] += 1
        return polls["n"] > 2

    monkeypatch.setattr(Request, "is_disconnected", hung_up_after_two_polls)
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 5.0)
    _script(monkeypatch, _missing)

    transport = httpx.ASGITransport(app=_app(RecordingPubSub()))
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:
        resp = await client.get("/scopes/live/policy")

    assert resp.status_code == 409
    assert _waits(emitted) == [{"outcome": "disconnected", "for": "branch"}]
    assert not [
        t for t, _ in emitted["event"] if t == "ScopePolicyUnavailable"
    ], "a client that had hung up still produced a 409 event"


def test_the_claims_are_bounded(monkeypatch):
    monkeypatch.setattr(scopes_api, "_BRANCH_REFRESH_TRACKED_MAX", 3)
    for n in range(5):
        scopes_api._record_branch_refresh(f"s{n}", float(n))
    assert list(scopes_api._branch_refresh_requested) == ["s2", "s3", "s4"]


def test_a_re_recorded_claim_is_the_newest(monkeypatch):
    """Mutation: dropping `move_to_end` evicts a, the scope just claimed again,
    instead of b."""
    monkeypatch.setattr(scopes_api, "_BRANCH_REFRESH_TRACKED_MAX", 2)
    for n, scope_id in enumerate("abac"):
        scopes_api._record_branch_refresh(scope_id, float(n))
    assert list(scopes_api._branch_refresh_requested) == ["a", "c"]


# --- a repoint fetches and always notifies -------------------------------


def _put(client, scope):
    return client.put("/scopes", json=scope.model_dump())


def test_put_marks_a_changed_or_unknown_source_as_a_repoint(monkeypatch):
    """A changed source, and a scope with no previous record (a sibling may
    have left the scope's old ref in a surviving clone), notify and force the
    fetch; an unchanged source keeps the caller's force_fetch."""
    monkeypatch.setattr(scopes_api, "verify_private_key_or_throw", lambda s: None)
    pubsub = RecordingPubSub()
    client = _client(pubsub, _scope(url="https://git/a.git"))

    assert _put(client, _scope(url="https://git/b.git")).status_code == 201
    assert _put(client, _scope(url="https://git/b.git")).status_code == 201
    assert _put(client, _scope("new", url="https://git/b.git")).status_code == 201

    assert [(d["repointed"], d["force_fetch"]) for d in pubsub.syncs()] == [
        (True, True),
        (False, False),
        (True, True),
    ]


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


@pytest.fixture
def clear_fetcher_caches():
    def clear():
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repo_locks.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.source_backoff.clear()

    clear()
    yield
    clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("repointed, publishes", [(False, 1), (True, 2)])
async def test_a_repoint_sync_of_an_unmoved_head_notifies(
    tmp_path, clear_fetcher_caches, repointed, publishes
):
    """End to end through the watcher, the service and a real clone of a local
    origin: the clone already holds the scope's ref at the branch head (what a
    move back to an earlier repository finds), so only a repoint notifies.

    Mutation: dropping `notify_all=notify_all` where sync_scope builds its
    callbacks makes the repoint case publish once."""
    remote = git.Repo.init(tmp_path / "remote", initial_branch="main")
    _commit(remote, "policy/a.rego", "package a\n")
    source = GitPolicyScopeSource(
        source_type="git", url=str(tmp_path / "remote"), auth=NoAuthData()
    )
    scope = Scope(scope_id="s", policy=source)
    pubsub = RecordingPubSub()
    service = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=pubsub,
    )
    await service.sync_scope(scope_id="s")  # clones; the first sync notifies
    assert len(pubsub.published) == 1

    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    task._service = service
    await task.trigger(
        None, {"scope_id": "s", "force_fetch": True, "repointed": repointed}
    )

    assert len(pubsub.published) == publishes


@pytest.mark.asyncio
@pytest.mark.parametrize("notify_all", [False, True])
async def test_on_update_names_every_directory_only_for_a_repoint(tmp_path, notify_all):
    """With a head that did move, a repoint still names every directory, not
    only the changed one: the client may have fetched from the other
    repository in between.

    Mutation: changing `previous_head is None or self._notify_all` back to
    `previous_head is None` fails the repoint case."""
    source = GitPolicyScopeSource(
        source_type="git", url="https://git/a.git", auth=NoAuthData()
    )
    repo = git.Repo.init(GitPolicyFetcher.repo_clone_path(tmp_path, source))
    _commit(repo, "one/a.rego", "package one\n")
    old = _commit(repo, "two/b.rego", "package two\n").hexsha
    head = _commit(repo, "one/a.rego", "package one\n\ndefault x := 1\n").hexsha
    pubsub = RecordingPubSub()
    callbacks = NewCommitsCallbacks(
        tmp_path, "s", source, pubsub, notify_all=notify_all
    )

    await callbacks.on_update(old, head)

    [(topics, _)] = pubsub.published
    named = " ".join(topics)
    assert "one" in named
    assert ("two" in named) is notify_all


@pytest.mark.asyncio
@pytest.mark.parametrize("notify_all, published", [(False, 0), (True, 1)])
async def test_an_unmoved_head_notifies_only_on_a_repoint(
    tmp_path, notify_all, published
):
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


# --- review round 2: bounds, riders, the cap after a publish ---------------


@pytest.mark.asyncio
async def test_a_rider_is_held_no_longer_than_the_first_requests_deadline(
    monkeypatch, emitted
):
    """A request that rides another's sync gets that request's deadline, not a
    fresh one: a branch that does not exist holds requests for at most one
    clone wait after the sync was requested.

    Mutation: giving a rider `now + wait` instead of `requested + wait` holds B
    for a full extra wait.
    """
    _script(monkeypatch, _missing)
    transport = httpx.ASGITransport(app=_app(RecordingPubSub()))
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:

        async def first_request():
            resp = await client.get("/scopes/live/policy")
            return resp, asyncio.get_running_loop().time()

        async def late_rider():
            # Arrives late in the first request's hold, so that its own
            # deadline would be well after the first request's.
            await asyncio.sleep(0.7 * WAIT)
            resp = await client.get("/scopes/live/policy")
            return resp, asyncio.get_running_loop().time()

        (first, first_done), (rider, rider_done) = await asyncio.gather(
            first_request(), late_rider()
        )

    assert first.status_code == rider.status_code == 409
    # Timed against the first request's end, not the rider's own start: both
    # end at the same deadline, and load delays both alike. The mutant ends
    # the rider about 0.7 * WAIT after the first.
    gap = rider_done - first_done
    assert gap < 0.35 * WAIT, f"the rider was held {gap:.2f}s past the first"
    # Both held to that deadline, not the rider released early.
    assert [w["outcome"] for w in _waits(emitted)] == ["timeout", "timeout"]


def test_a_branch_miss_late_in_a_clone_wait_keeps_the_clone_waits_deadline(
    monkeypatch,
):
    """The in-loop `min`: a clone that lands without the branch late in its
    wait does not restart the budget, which is clamped below the load
    balancer's idle timeout.

    Mutation: `deadline = branch_deadline` instead of the `min` polls well
    past the budget and fails the bound on the polls.
    """
    poll = 0.02
    calls = _script(monkeypatch, *([_populating] * 10 + [_missing]))

    resp = _client(RecordingPubSub()).get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(calls) <= WAIT / poll + 2, f"{len(calls)} polls for a {WAIT}s budget"


@pytest.mark.asyncio
async def test_an_in_loop_miss_without_a_sync_ends_as_the_clone_wait_it_was(
    monkeypatch, emitted
):
    """The clone lands without the branch, and the request may not wait for it
    (here: no sync can be requested, as on the default-scope path).

    It is the clone wait's end: counted `for: clone`, and its hold is
    carried to the 409 so the route reports it.
    """
    _script(monkeypatch, _populating, _populating, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)

    with pytest.raises(BranchHeadNotFoundError) as raised:
        await scopes_api._make_bundle_waiting_for_clone(fetcher, None, "live")

    assert raised.value.waited_seconds > 0
    assert _waits(emitted) == [{"outcome": "error", "for": "clone"}]
    # Mutation: settling the miss without the `request_refresh is None` guard
    # counts a failed publish for a sync this path never asks for.
    assert _refreshes(emitted) == []


def test_an_in_loop_miss_after_the_sync_had_its_chance_is_answered_at_once(
    monkeypatch, emitted
):
    pubsub = RecordingPubSub()
    client = _client(pubsub)
    _script(monkeypatch, _missing)
    assert client.get("/scopes/live/policy").status_code == 409  # its chance

    calls = _script(monkeypatch, _populating, _missing, _ready)
    resp = client.get("/scopes/live/policy")

    assert resp.status_code == 409
    assert len(calls) == 2, "the miss was held after its sync had had its chance"
    assert len(pubsub.syncs()) == 1
    assert _waits(emitted)[-1] == {"outcome": "error", "for": "clone"}


@pytest.mark.asyncio
async def test_riders_of_a_failed_publish_are_released(monkeypatch, emitted):
    """A request that rides a sync whose publish then fails is not held for a
    sync nobody requested: at its next poll it gets the 409.

    Mutation: dropping the rider's claim check holds it until the first
    request's deadline (outcome timeout).
    """
    pubsub = SlowPubSub(delay=0.1, fail=True)
    _script(monkeypatch, _missing)
    transport = httpx.ASGITransport(app=_app(pubsub))
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:

        async def rider():
            await asyncio.sleep(0.03)
            started = asyncio.get_running_loop().time()
            resp = await client.get("/scopes/live/policy")
            return resp, asyncio.get_running_loop().time() - started

        first, (ridden, elapsed) = await asyncio.gather(
            client.get("/scopes/live/policy"), rider()
        )

    assert first.status_code == ridden.status_code == 409
    assert elapsed < 0.6 * WAIT, f"the rider was held {elapsed:.2f}s"
    assert {"outcome": "unrequested", "for": "branch"} in _waits(emitted)


@pytest.mark.asyncio
async def test_the_cap_is_checked_again_after_a_publish(monkeypatch, emitted):
    """Two scopes' first misses both pass the cap check, then yield in their
    publishes; only one may take the last slot.

    Mutation: dropping the second cap check lets both in, past the cap.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 1)
    peak = {"n": 0}
    real = scopes_api._publish_clone_wait_inflight

    def tracking():
        peak["n"] = max(peak["n"], scopes_api._clone_wait_inflight)
        real()

    monkeypatch.setattr(scopes_api, "_publish_clone_wait_inflight", tracking)
    gate = _gate(monkeypatch)
    transport = httpx.ASGITransport(app=_app(SlowPubSub(), _scope("a"), _scope("b")))
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:

        async def open_soon():
            await asyncio.sleep(0.15)
            gate["open"] = True

        a, b, _ = await asyncio.gather(
            client.get("/scopes/a/policy"), client.get("/scopes/b/policy"), open_soon()
        )

    assert sorted([a.status_code, b.status_code]) == [200, 409]
    assert peak["n"] <= 1, f"{peak['n']} requests held under a cap of 1"
    assert {"outcome": "shed", "for": "branch"} in _waits(emitted)


@pytest.mark.asyncio
async def test_a_burst_for_a_missing_branch_costs_one_fetch(monkeypatch, tmp_path):
    """A fetch that started after a sync request arrived already looked for the
    branch, so that request does not fetch again.

    Mutation: dropping the `_was_fetched_after(req_time)` check in the
    missing-branch arm of `_should_fetch` fetches for every request.
    """
    fetcher = GitPolicyFetcher(Path(tmp_path), "live", _scope().policy)
    monkeypatch.setattr(
        "opal_server.git_fetcher.RepoInterface.has_remote_branch",
        lambda *a, **k: False,
    )
    asked = datetime.datetime.now()
    GitPolicyFetcher.repos_last_fetched.pop(fetcher._source_id, None)
    try:
        assert await fetcher._should_fetch(None, req_time=asked) is True
        GitPolicyFetcher.repos_last_fetched[
            fetcher._source_id
        ] = asked + datetime.timedelta(seconds=1)
        assert await fetcher._should_fetch(None, req_time=asked) is False
        # Without a request time (a pass), the missing branch is still fetched.
        assert await fetcher._should_fetch(None) is True
    finally:
        GitPolicyFetcher.repos_last_fetched.pop(fetcher._source_id, None)


@pytest.mark.asyncio
async def test_the_trigger_passes_the_backoff_flag_on():
    seen = []

    class Service:
        async def sync_scope(self, **kwargs):
            seen.append(kwargs)
            return None

    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    task._service = Service()
    await task.trigger(None, {"scope_id": "s", "honor_backoff": True})
    await task.trigger(None, {"scope_id": "s"})

    assert [k["honor_backoff"] for k in seen] == [True, False]


# --- what is served and stored stays the scope's own -----------------------
#
# Real clones of a local origin, no mocked git: the claims the change rests on
# for the policy a client ends up with.


def _shared_bed(tmp_path):
    """An origin with `main`, and a service whose clone of it is shared by
    every scope on it (the default single shard)."""
    origin = git.Repo.init(tmp_path / "origin", initial_branch="main")
    _commit(origin, "policy/app.rego", 'package app\n\nmarker := "main"\n')
    return origin, str(tmp_path / "origin")


def _git_scope(scope_id, url, branch):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch=branch, auth=NoAuthData()
        ),
    )


def _push_branch(origin, branch, marker):
    """Create ``branch`` on the origin from main, with its own marker; return
    its head."""
    origin.git.checkout("-b", branch, "main")
    head = _commit(
        origin, "policy/app.rego", f'package app\n\nmarker := "{marker}"\n'
    ).hexsha
    origin.git.checkout("main")
    return head


def _rego(bundle):
    return [m.rego for m in bundle.policy_modules]


class SyncingPubSub(RecordingPubSub):
    """Delivers the webhook topic to a watcher task, as the broadcaster does on
    every leader, and records everything."""

    def __init__(self, task):
        super().__init__()
        self._task = task
        self.syncs_running = []

    async def publish(self, topics, data=None):
        await super().publish(topics, data)
        if topics == opal_server_config.POLICY_REPO_WEBHOOK_TOPIC:
            self.syncs_running.append(
                asyncio.ensure_future(self._task.trigger(topics, data))
            )


@pytest.mark.asyncio
async def test_a_held_request_is_served_exactly_its_own_branch(
    tmp_path, monkeypatch, clear_fetcher_caches
):
    """A pod that missed a PUT's broadcast: the scope's record names a branch
    its shared clone has never fetched. The request is held, its sync fetches,
    and the bundle is the branch's own head, byte for byte, not the content of
    the other branch living in the same clone; the other scope's bundle is
    unchanged by the fetch.

    Mutation: building the bundle from any ref but the scope's branch head
    (the scope ref, or the clone's checked-out branch) fails the content or
    hash assertions.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 20.0)
    origin, url = _shared_bed(tmp_path)
    main_head = origin.head.commit.hexsha
    warm = _git_scope("warm", url, "main")
    scopes = FakeScopeRepository([warm])
    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    pubsub = SyncingPubSub(task)
    service = ScopesService(base_dir=tmp_path, scopes=scopes, pubsub_endpoint=pubsub)
    task._service = service
    await service.sync_scope(scope_id="warm")  # the clone, with main only

    env_head = _push_branch(origin, "env2", "env2")
    # The record a pod that missed the broadcast holds: no sync of it ran here.
    await scopes.put(_git_scope("moved", url, "env2"))

    app = FastAPI()
    app.include_router(
        init_scope_router(scopes, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:
        moved = await client.get("/scopes/moved/policy")
        still = await client.get("/scopes/warm/policy")
    await asyncio.gather(*pubsub.syncs_running)

    assert moved.status_code == 200, moved.text
    moved_bundle = PolicyBundle(**moved.json())
    assert moved_bundle.hash == env_head
    assert _rego(moved_bundle) == ['package app\n\nmarker := "env2"\n']

    assert still.status_code == 200
    warm_bundle = PolicyBundle(**still.json())
    assert warm_bundle.hash == main_head
    assert _rego(warm_bundle) == ['package app\n\nmarker := "main"\n']

    # The fetched branch is the origin's, commit for commit.
    clone = git.Repo(GitPolicyFetcher.repo_clone_path(tmp_path, warm.policy))
    assert clone.commit("refs/remotes/origin/env2").hexsha == env_head
    assert clone.commit("refs/remotes/origin/main").hexsha == main_head


@pytest.mark.asyncio
async def test_a_coalesced_sync_finds_a_branch_another_scopes_fetch_brought(
    tmp_path, monkeypatch, clear_fetcher_caches
):
    """The coalescing in `_should_fetch` skips a fetch for a branch missing
    from the clone only when a fetch of the same clone started after the
    request. That is sound because a fetch brings every branch, whichever
    scope asked for it: a branch the origin had when such a fetch started is
    in the clone, so the skip is reached only for a branch the origin did not
    have after the request arrived. Here the sync after another scope's fetch
    finds its branch, at the origin's head, without fetching, and notifies its
    clients. A fetch that started BEFORE the request does not count, nor does
    one under way when the branch was pushed.

    Mutation: a fetch narrowed to the asking scope's branch fails the first
    part; treating any earlier fetch as an answer fails the second; recording
    a fetch's completion time instead of its start fails the third. Dropping
    the coalescing is test_a_burst_for_a_missing_branch_costs_one_fetch's."""
    origin, url = _shared_bed(tmp_path)
    scopes = FakeScopeRepository([_git_scope("warm", url, "main")])
    pubsub = RecordingPubSub()
    service = ScopesService(base_dir=tmp_path, scopes=scopes, pubsub_endpoint=pubsub)
    await service.sync_scope(scope_id="warm")
    source_id = GitPolicyFetcher.source_id(_git_scope("warm", url, "main").policy)

    # 1. The branch is pushed, the request arrives, then another scope's
    #    forced sync fetches the shared clone.
    env2_head = _push_branch(origin, "env2", "env2")
    await scopes.put(_git_scope("s2", url, "env2"))
    asked = datetime.datetime.now()
    await service.sync_scope(scope_id="warm", force_fetch=True)
    fetched_at = GitPolicyFetcher.repos_last_fetched[source_id]
    assert fetched_at > asked
    published = len(pubsub.published)

    await service.sync_scope(scope_id="s2", req_time=asked)

    assert (
        GitPolicyFetcher.repos_last_fetched[source_id] == fetched_at
    ), "the coalesced sync fetched again"
    assert len(pubsub.published) == published + 1, "s2's clients were not told"
    clone = git.Repo(
        GitPolicyFetcher.repo_clone_path(tmp_path, scopes._scopes["s2"].policy)
    )
    assert clone.commit("refs/remotes/origin/env2").hexsha == env2_head

    # 2. A branch pushed after the last fetch started, asked for after the
    #    push: that fetch does not answer the request, so the sync fetches.
    env3_head = _push_branch(origin, "env3", "env3")
    await scopes.put(_git_scope("s3", url, "env3"))
    asked = datetime.datetime.now()
    assert fetched_at < asked

    await service.sync_scope(scope_id="s3", req_time=asked)

    assert GitPolicyFetcher.repos_last_fetched[source_id] > asked
    assert clone.commit("refs/remotes/origin/env3").hexsha == env3_head

    # 3. A branch pushed WHILE a fetch runs, after that fetch read the
    #    origin's refs, and asked for before it completes: the fetch did not
    #    bring it, so it must not count as answering the request. This is why
    #    the fetch's start time is recorded, not its completion.
    real_executor = git_fetcher_module.run_in_git_executor
    during = {}

    async def executor(func, *args, **kwargs):
        result = await real_executor(func, *args, **kwargs)
        if during.pop("arm", False):
            during["head"] = _push_branch(origin, "env4", "env4")
            during["asked"] = datetime.datetime.now()
        return result

    monkeypatch.setattr(git_fetcher_module, "run_in_git_executor", executor)
    during["arm"] = True
    await service.sync_scope(scope_id="warm", force_fetch=True)
    assert "head" in during, "the fetch did not run"
    await scopes.put(_git_scope("s4", url, "env4"))

    await service.sync_scope(scope_id="s4", req_time=during["asked"])

    assert clone.commit("refs/remotes/origin/env4").hexsha == during["head"]


@pytest.mark.asyncio
async def test_a_repoint_whose_fetch_fails_tells_nobody(tmp_path, clear_fetcher_caches):
    """A repoint forces the fetch so that its update-all never names a stale
    head. When that fetch fails, nothing is published and the scope's ref
    does not move: a client is not sent back to whatever the clone held from
    the last time the scope used this repository.

    Mutation: notifying before the fetch, or on its failure, publishes."""
    origin, url = _shared_bed(tmp_path)
    scope = _git_scope("s", url, "main")
    pubsub = RecordingPubSub()
    service = ScopesService(
        base_dir=tmp_path, scopes=FakeScopeRepository([scope]), pubsub_endpoint=pubsub
    )
    await service.sync_scope(scope_id="s")
    assert len(pubsub.published) == 1
    clone = git.Repo(GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy))
    ref_before = clone.commit("scopes/s").hexsha

    _commit(origin, "policy/app.rego", 'package app\n\nmarker := "newer"\n')
    (tmp_path / "origin").rename(tmp_path / "gone")  # the remote is unreachable

    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    task._service = service
    await task.trigger(None, {"scope_id": "s", "force_fetch": True, "repointed": True})

    # The fetch was attempted, and failed: a failed fetch records a backoff.
    assert GitPolicyFetcher.source_id(scope.policy) in GitPolicyFetcher.source_backoff
    assert len(pubsub.published) == 1, "a failed repoint fetch notified clients"
    assert clone.commit("scopes/s").hexsha == ref_before


def test_put_stores_the_record_exactly_as_sent(monkeypatch):
    """The change adds keys to the sync message PUT /scopes publishes, and
    nothing else: the stored record, its data entries included, is the request
    body, and the repoint purge names the old source as before."""
    monkeypatch.setattr(scopes_api, "verify_private_key_or_throw", lambda s: None)
    old = _scope(url="https://git/a.git")
    new = Scope(
        scope_id="live",
        policy=GitPolicyScopeSource(
            source_type="git",
            url="https://git/b.git",
            branch="env",
            auth=NoAuthData(auth_type="none"),
            directories=["policy"],
        ),
        data={
            "entries": [
                {
                    "url": "https://data.example/v1/facts",
                    "topics": ["policy_data"],
                    "dst_path": "/facts",
                }
            ]
        },
    )
    repo = FakeScopeRepository([old])
    pubsub = RecordingPubSub()
    service = ScopesService(
        base_dir=Path("/unused"), scopes=repo, pubsub_endpoint=pubsub
    )
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), pubsub, service), prefix="/scopes"
    )

    assert TestClient(app).put("/scopes", json=new.model_dump()).status_code == 201

    assert repo._scopes["live"] == new
    assert repo._scopes["live"].model_dump() == new.model_dump()
    purges = [
        d for t, d in pubsub.published if t == [opal_server_config.SCOPES_PURGE_CHANNEL]
    ]
    assert [(p["source_id"], p["reason"]) for p in purges] == [
        (GitPolicyFetcher.source_id(old.policy), "repoint")
    ]


# --- review round 3: what a hold costs, a missing clone, pruning, claims -----


async def _until(condition, timeout=5.0):
    """Polls ``condition`` under a deadline, so a regression fails, not
    hangs."""

    async def poll():
        while not condition():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), timeout)


def _route_app(scopes, pubsub, service):
    app = FastAPI()
    app.include_router(
        init_scope_router(scopes, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://bed"
    )


@pytest.mark.asyncio
async def test_a_held_poll_is_one_ref_lookup(
    tmp_path, monkeypatch, clear_fetcher_caches
):
    """A held request polls the scope's one remote-tracking ref and builds a
    bundle only once it is there, and nothing on its path lists every ref: on a
    clone of a repository with tens of thousands of branches, a listing costs
    seconds, on the shared executor. The miss is logged once, by the route's
    409.

    Mutation: polling make_bundle (as before) builds once per poll, lists
    every ref each time, and logs an ERROR per poll.
    """
    origin, url = _shared_bed(tmp_path)
    warm = _git_scope("warm", url, "main")
    scopes = FakeScopeRepository([warm, _git_scope("moved", url, "env2")])
    pubsub = RecordingPubSub()  # the sync is requested, and never runs
    service = ScopesService(base_dir=tmp_path, scopes=scopes, pubsub_endpoint=pubsub)
    await service.sync_scope(scope_id="warm")  # the clone, without env2

    builds = []
    real_make_bundle = GitPolicyFetcher.make_bundle

    def counting_make_bundle(self, base_hash=None):
        builds.append(base_hash)
        return real_make_bundle(self, base_hash)

    listings = []
    real_listall = pygit2.Repository.listall_references

    def counting_listall(self):
        listings.append(1)
        return real_listall(self)

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", counting_make_bundle)
    monkeypatch.setattr(pygit2.Repository, "listall_references", counting_listall)

    with capture_records() as logs:
        async with _route_app(scopes, pubsub, service) as client:
            resp = await client.get("/scopes/moved/policy")

    assert resp.status_code == 409
    assert len(pubsub.syncs()) == 1
    assert len(builds) == 1, f"{len(builds)} bundle builds for one held request"
    assert listings == [], "a held request listed every ref in the clone"
    errors = [r for r in logs.emitted if r["level"].name == "ERROR"]
    assert len(errors) == 1, [r["message"] for r in errors]


@pytest.mark.asyncio
async def test_a_pod_without_the_clone_requests_a_sync_and_is_served(
    tmp_path, monkeypatch, clear_fetcher_caches
):
    """A scope moved to a repository this pod has never cloned, on a pod that
    missed the PUT's broadcast: the request asks for the sync, which clones,
    and is served.

    Mutation: answering NoSuchPathError at once (as before) returns the 503
    with no sync requested.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 20.0)
    origin, url = _shared_bed(tmp_path)
    scopes = FakeScopeRepository([_git_scope("moved", url, "main")])
    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    pubsub = SyncingPubSub(task)
    service = ScopesService(base_dir=tmp_path, scopes=scopes, pubsub_endpoint=pubsub)
    task._service = service

    async with _route_app(scopes, pubsub, service) as client:
        resp = await client.get("/scopes/moved/policy")
    await asyncio.gather(*pubsub.syncs_running)

    assert resp.status_code == 200, resp.text
    assert PolicyBundle(**resp.json()).hash == origin.head.commit.hexsha
    assert len(pubsub.syncs()) == 1


@pytest.mark.asyncio
async def test_a_pod_without_the_clone_answers_503_once_the_hold_runs_out(
    tmp_path, emitted, clear_fetcher_caches
):
    """The sync is requested but no clone appears: the request gets the
    retryable 503 it got before, after the hold."""
    pubsub = RecordingPubSub()
    scopes = FakeScopeRepository([_git_scope("moved", str(tmp_path / "none"), "main")])
    service = ScopesService(base_dir=tmp_path, scopes=scopes, pubsub_endpoint=pubsub)

    async with _route_app(scopes, pubsub, service) as client:
        resp = await client.get("/scopes/moved/policy")

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"
    assert len(pubsub.syncs()) == 1
    assert _waits(emitted) == [{"outcome": "timeout", "for": "branch"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("prune", [True, False])
async def test_a_branch_deleted_on_the_remote_leaves_the_clone(
    tmp_path, clear_fetcher_caches, monkeypatch, prune
):
    """With SCOPES_GIT_FETCH_PRUNE on, a fetch prunes the remote-tracking ref
    of a branch the remote deleted, so the scope that names it misses (and a
    bundle request waits for the branch) instead of being served the deleted
    branch's last head. The scopes' own refs/heads/scopes/* refs are not
    pruned.

    Mutation: fetching without prune keeps refs/remotes/origin/env2, and its
    stale head is served.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", prune)
    origin, url = _shared_bed(tmp_path)
    _push_branch(origin, "env2", "env2")
    warm = _git_scope("warm", url, "main")
    moved = _git_scope("moved", url, "env2")
    service = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([warm, moved]),
        pubsub_endpoint=RecordingPubSub(),
    )
    await service.sync_scope(scope_id="warm")
    await service.sync_scope(scope_id="moved")
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, warm.policy))

    def refs():
        repo = pygit2.Repository(clone_path)
        try:
            return set(repo.listall_references())
        finally:
            repo.free()

    scope_refs = {r for r in refs() if r.startswith("refs/heads/scopes/")}
    assert scope_refs == {"refs/heads/scopes/warm", "refs/heads/scopes/moved"}
    assert "refs/remotes/origin/env2" in refs()

    origin.git.branch("-D", "env2")
    await service.sync_scope(scope_id="warm", force_fetch=True)

    after = refs()
    assert "refs/remotes/origin/main" in after
    assert scope_refs <= after, "a scope's own ref was pruned"
    if not prune:
        # The default: the stale ref stays, and is what a bundle is built from.
        assert "refs/remotes/origin/env2" in after
        GitPolicyFetcher(tmp_path, "moved", moved.policy).make_bundle()
        return
    assert "refs/remotes/origin/env2" not in after
    with pytest.raises(BranchHeadNotFoundError):
        GitPolicyFetcher(tmp_path, "moved", moved.policy).make_bundle()


@pytest.mark.asyncio
async def test_a_publish_that_does_not_return_is_bounded_by_the_hold(
    monkeypatch, emitted
):
    """A slow broadcast backend does not hold the request past its hold, and
    the claim is kept, since the publish may still go out.

    Mutation: awaiting the publish unbounded never answers (the test's own
    deadline fails it).
    """
    stuck = asyncio.Event()

    async def never_returns():
        await stuck.wait()

    _script(monkeypatch, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)
    loop = asyncio.get_running_loop()
    started = loop.time()

    with pytest.raises(BranchHeadNotFoundError) as raised:
        await asyncio.wait_for(
            scopes_api._make_bundle_waiting_for_clone(
                fetcher, None, "live", request_refresh=never_returns
            ),
            5 * WAIT,
        )

    assert loop.time() - started < 2 * WAIT
    assert _refreshes(emitted) == ["publish_timeout"]
    # Still a wait, reported as one.
    assert _waits(emitted) == [{"outcome": "timeout", "for": "branch"}]
    assert raised.value.waited_seconds >= 0.9 * WAIT
    assert "live" in scopes_api._branch_refresh_requested
    [publish] = scopes_api._branch_refresh_publishes  # still referenced
    stuck.set()
    await publish
    assert not scopes_api._branch_refresh_publishes


@pytest.mark.asyncio
async def test_a_failed_publish_gives_back_only_its_own_claim(monkeypatch, emitted):
    """It restores the claim it replaced, and leaves a newer one alone: the
    requests holding for either are not its to release.

    Mutation: popping the scope's entry on any failed publish (as before)
    drops both.
    """
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", WAIT / 3
    )
    claims = scopes_api._branch_refresh_requested

    async def fails():
        raise ConnectionError("no local subscriber")

    loop = asyncio.get_running_loop()

    # The claim it replaced, older than the interval, comes back.
    now = loop.time()
    claims["live"] = now - WAIT
    assert (
        await scopes_api._branch_wait_claim("live", fails, now, WAIT, now + WAIT)
        is None
    )
    assert claims["live"] == now - WAIT

    # A newer claim recorded while it was publishing stays.
    release = asyncio.Event()

    async def fails_late():
        await release.wait()
        raise ConnectionError("no local subscriber")

    now = loop.time()
    pending = asyncio.ensure_future(
        scopes_api._branch_wait_claim("live", fails_late, now, WAIT, now + WAIT)
    )
    await _until(lambda: claims.get("live") == now)  # its claim is recorded
    claims["live"] = now + 1.0  # a newer request's
    release.set()
    assert await pending is None
    assert claims["live"] == now + 1.0
    assert _refreshes(emitted) == ["publish_failed", "publish_failed"]


@pytest.mark.asyncio
async def test_a_branch_that_lands_as_the_claim_goes_is_served(monkeypatch, emitted):
    """The release check runs after the bundle attempt: a branch that arrives
    at the poll that would find the claim gone is served, not answered 409.

    Mutation: checking the claim before the attempt (as before) answers 409.
    """

    class WithdrawnAfterOnePoll(OrderedDict):
        """The claim is seen by the rider's hold decision and by its first
        poll, then given back (another request's publish failed)."""

        reads = 0

        def get(self, key, default=None):
            self.reads += 1
            return super().get(key, default) if self.reads <= 2 else default

    claims = WithdrawnAfterOnePoll()
    # A rider: the sync was requested by another request just now.
    claims["live"] = asyncio.get_running_loop().time()
    monkeypatch.setattr(scopes_api, "_branch_refresh_requested", claims)
    _script(monkeypatch, _missing, _missing, _ready)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)

    async def not_asked():
        raise AssertionError("a rider requested a sync")

    bundle = await scopes_api._make_bundle_waiting_for_clone(
        fetcher, None, "live", request_refresh=not_asked
    )

    assert bundle.hash == "head"
    assert _waits(emitted) == [{"outcome": "served", "for": "branch"}]


def _hold(fetcher, request_refresh):
    return asyncio.ensure_future(
        scopes_api._make_bundle_waiting_for_clone(
            fetcher, None, "live", request_refresh=request_refresh
        )
    )


async def _not_asked():
    raise AssertionError("a rider requested a sync")


@pytest.mark.asyncio
async def test_a_publish_that_fails_after_its_hold_is_given_back_and_reported(
    monkeypatch, emitted
):
    """Mutation: only retrieving the exception (as before) leaves the claim for
    the whole interval, with every miss riding a sync that was never sent, and
    nothing counted or logged."""
    release = asyncio.Event()

    async def fails_late():
        await release.wait()
        raise ConnectionError("no local subscriber")

    _script(monkeypatch, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)

    with pytest.raises(BranchHeadNotFoundError):
        await _hold(fetcher, fails_late)
    assert "live" in scopes_api._branch_refresh_requested

    with capture_records() as logs:
        release.set()
        await _until(lambda: "publish_failed" in _refreshes(emitted))

    assert "live" not in scopes_api._branch_refresh_requested
    assert _refreshes(emitted) == ["publish_timeout", "publish_failed"]
    assert [r for r in logs.emitted if r["level"].name == "WARNING"]


@pytest.mark.asyncio
async def test_a_publish_that_raises_timeout_error_itself_is_a_failed_publish(
    monkeypatch, emitted
):
    """Mutation: `wait_for` (as before) takes it for the hold running out on
    3.11+: the claim is kept and the request held for a sync never sent."""

    async def times_out():
        raise TimeoutError("the broadcast backend timed out")

    _script(monkeypatch, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)

    with pytest.raises(BranchHeadNotFoundError) as raised:
        await _hold(fetcher, times_out)

    assert raised.value.waited_seconds == 0.0
    assert _refreshes(emitted) == ["publish_failed"]
    assert "live" not in scopes_api._branch_refresh_requested


@pytest.mark.asyncio
async def test_riders_of_a_failed_publish_are_released_when_it_restores_a_claim(
    monkeypatch, emitted
):
    """The failed publish puts back the older claim it replaced, so the entry
    is there, but older than the claim its riders hold for.

    Mutation: releasing only on `current is None` holds the rider until its
    deadline.
    """
    claims = scopes_api._branch_refresh_requested
    loop = asyncio.get_running_loop()
    # Older than the fixture's 60 s interval: the first miss requests a sync.
    seeded = claims["live"] = loop.time() - 120.0
    release = asyncio.Event()

    async def fails_when_released():
        await release.wait()
        raise ConnectionError("no local subscriber")

    _script(monkeypatch, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)

    first = _hold(fetcher, fails_when_released)
    await _until(lambda: claims["live"] != seeded)
    rider = _hold(fetcher, _not_asked)
    await _until(lambda: scopes_api._clone_wait_inflight == 1)
    release.set()

    with pytest.raises(BranchHeadNotFoundError):
        await first
    with pytest.raises(BranchHeadNotFoundError) as raised:
        await rider

    assert claims["live"] == seeded
    assert raised.value.waited_seconds < 0.6 * WAIT
    assert _waits(emitted) == [{"outcome": "unrequested", "for": "branch"}]


@pytest.mark.asyncio
async def test_a_newer_claim_does_not_release_a_request_holding_for_an_older_one(
    monkeypatch, emitted
):
    """An interval shorter than the wait: a later miss records a claim of its
    own, and the sync the first request holds for did go out.

    Mutation: releasing on `current != claim` ends the first request
    `unrequested`.
    """
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", WAIT / 3
    )
    claims = scopes_api._branch_refresh_requested
    loop = asyncio.get_running_loop()
    requested = []

    async def publishes():
        requested.append(loop.time())

    _script(monkeypatch, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)

    first = _hold(fetcher, publishes)
    await _until(lambda: requested)
    claimed = claims["live"]
    await _until(lambda: loop.time() - claimed >= WAIT / 3)
    later = _hold(fetcher, publishes)

    for held in (first, later):
        with pytest.raises(BranchHeadNotFoundError):
            await held

    assert len(requested) == 2
    assert _waits(emitted) == [{"outcome": "timeout", "for": "branch"}] * 2


@pytest.mark.asyncio
async def test_an_in_loop_publish_is_bounded_by_the_clone_waits_deadline(
    monkeypatch, emitted
):
    """Mutation: passing a later deadline to the in-loop `_branch_wait_claim`
    holds the request past the clone wait's budget."""
    stuck = asyncio.Event()

    async def never_returns():
        await stuck.wait()

    _script(monkeypatch, _populating, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)
    loop = asyncio.get_running_loop()
    started = loop.time()

    with pytest.raises(BranchHeadNotFoundError):
        await asyncio.wait_for(_hold(fetcher, never_returns), 5 * WAIT)

    assert loop.time() - started < 2 * WAIT
    assert _refreshes(emitted) == ["publish_timeout"]
    [publish] = scopes_api._branch_refresh_publishes
    stuck.set()
    await publish


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_a_request_cancelled_in_its_publish(monkeypatch, emitted, fails):
    """The client goes away while the sync request is being published: the
    publish still ends, and the claim stands unless it then fails.

    Mutation: not watching the publish on cancellation leaves a late failure
    unreported, with the claim kept.
    """
    release = asyncio.Event()

    async def publishes():
        await release.wait()
        if fails:
            raise ConnectionError("no local subscriber")

    _script(monkeypatch, _missing)
    fetcher = GitPolicyFetcher(Path("/unused"), "live", _scope().policy)
    held = _hold(fetcher, publishes)
    await _until(lambda: scopes_api._branch_refresh_publishes)

    held.cancel()
    with pytest.raises(asyncio.CancelledError):
        await held
    assert "live" in scopes_api._branch_refresh_requested
    assert scopes_api._clone_wait_inflight == 0

    release.set()
    await _until(lambda: not scopes_api._branch_refresh_publishes)

    assert ("live" in scopes_api._branch_refresh_requested) is not fails
    assert _refreshes(emitted) == (["publish_failed"] if fails else [])
