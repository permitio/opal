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
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.monitoring import metrics
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
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
    yield
    assert scopes_api._clone_wait_inflight == 0, "a wait slot leaked"


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
    """make_bundle plays ``outcomes`` in order, the last one repeating."""
    calls = []

    def fake(self, base_hash=None):
        calls.append(base_hash)
        return outcomes[min(len(calls) - 1, len(outcomes) - 1)]()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
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
    monkeypatch,
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

        async def late_rider():
            await asyncio.sleep(0.7 * WAIT)
            started = asyncio.get_running_loop().time()
            resp = await client.get("/scopes/live/policy")
            return resp, asyncio.get_running_loop().time() - started

        first, (rider, rider_elapsed) = await asyncio.gather(
            client.get("/scopes/live/policy"), late_rider()
        )

    assert first.status_code == rider.status_code == 409
    assert rider_elapsed < 0.6 * WAIT, f"the rider was held {rider_elapsed:.2f}s"


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
