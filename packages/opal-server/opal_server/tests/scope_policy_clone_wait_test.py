"""GET /scopes/:scope_id/policy holds a bounded wait while the clone is being
populated, instead of answering 503 the instant it finds an empty clone.

The 503 is honest but useless to the caller that matters: opal-client 0.9.6
ignores Retry-After. It makes five attempts with random-exponential backoff
capped at 10s (~20-40s of coverage) and then goes quiet until the next pub/sub
policy message or a reconnect. A clone that outlives those attempts leaves the
PDP with no policy and nothing scheduled to fix it — and the update-all
notification published when the clone finishes only names the scope that was
syncing, so siblings on the same shard get nothing.

Holding the request turns that gap into latency the client already tolerates.
Every test below names the single-line mutation it catches.
"""
import asyncio
import time

import pygit2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from git import NoSuchPathError
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
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

_WAIT_METRIC = "opal_server.scopes.policy_clone_wait"


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


def _client(repo, base_dir):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=None)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), None, service),
        prefix="/scopes",
    )
    return TestClient(app)


# --- outcomes a scripted make_bundle can produce -------------------------


def _populating():
    """The clone dir exists but has no refs/remotes/<remote>/* yet."""
    raise CloneNotPopulatedError("No refs/remotes/origin/* yet")


def _ready():
    return PolicyBundle(
        manifest=[], hash="cloned-head", data_modules=[], policy_modules=[]
    )


def _wrong_branch():
    raise BranchHeadNotFoundError("Could not find current branch head")


def _object_store_broken():
    raise pygit2.GitError("odb: object not found")


def _clone_dir_gone():
    raise NoSuchPathError("/var/lib/opal/clone")


def _scripted_make_bundle(*outcomes):
    """Install a make_bundle that plays `outcomes` in order.

    The LAST outcome repeats for every further attempt, so a one-element
    script means "this never changes". Returns the list of recorded
    calls (one entry per attempt) so a test can assert how many attempts
    the route actually made.
    """
    calls = []

    def fake_make_bundle(self, base_hash=None):
        calls.append(base_hash)
        return outcomes[min(len(calls) - 1, len(outcomes) - 1)]()

    return fake_make_bundle, calls


@pytest.fixture
def bed(tmp_path, monkeypatch):
    """A route under test with the wait tuned down to test timescales.

    The poll interval is patched (not the production 1s) so a full expiry
    costs a fifth of a second of wall clock rather than twenty seconds. The
    wait itself is real: no clock is faked, so the deadline arithmetic under
    test is the arithmetic that runs in production.
    """
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    class Bed:
        wait = 0.2

        def __init__(self):
            self.set_wait(self.wait)
            self.set_poll(0.02)

        def set_wait(self, seconds):
            self.wait = seconds
            monkeypatch.setattr(
                opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", seconds
            )

        def set_poll(self, seconds):
            monkeypatch.setattr(
                "opal_server.scopes.api._CLONE_WAIT_POLL_SECONDS", seconds
            )

        def run(self, *outcomes, scope_id="live"):
            fake, calls = _scripted_make_bundle(*outcomes)
            monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
            client = _client(FakeScopeRepository([_scope(scope_id)]), tmp_path)
            started = time.monotonic()
            resp = client.get(f"/scopes/{scope_id}/policy")
            return resp, calls, time.monotonic() - started

    return Bed()


@pytest.fixture
def emitted(monkeypatch):
    """Capture the metrics facade, patched on the module object: every emitter
    does `from opal_common.monitoring import metrics`, so they share it."""
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
    return calls


def _wait_outcomes(emitted):
    return [
        (tags or {}).get("outcome")
        for metric, tags in emitted["increment"]
        if metric == _WAIT_METRIC
    ]


@pytest.fixture
def sleeps(monkeypatch):
    """Record every awaited sleep duration, without shortening any of them.

    Recording rather than stubbing keeps the bound honest: the assertion
    "the sum of what we slept never exceeds the configured wait" is only
    worth making against the durations the route really asked for.
    """
    recorded = []
    real_sleep = asyncio.sleep

    async def recording_sleep(delay, *args, **kwargs):
        recorded.append(delay)
        return await real_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", recording_sleep)
    return recorded


# --- tests ---------------------------------------------------------------


def test_wait_disabled_answers_503_after_a_single_attempt(bed, emitted, sleeps):
    """0 must mean exactly the pre-wait behaviour, as an escape hatch that is
    worth having only if it is truly identical.

    Mutation: dropping the `if wait <= 0: raise` guard makes the route poll
    (deadline == now, so at least the sleep-and-retry setup runs) and the
    single-attempt assertion fails.
    """
    bed.set_wait(0)

    resp, calls, _ = bed.run(_populating)

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "30"
    assert len(calls) == 1, f"wait=0 still retried make_bundle: {len(calls)} attempts"
    assert not sleeps, f"wait=0 still slept: {sleeps}"
    assert not _wait_outcomes(emitted), "a wait that never happened was counted"


def test_clone_that_finishes_mid_wait_is_served_instead_of_503(bed, emitted, sleeps):
    """The whole point: a clone that completes inside the budget produces a
    200, not a 503 the client will not act on.

    Mutation: returning the first CloneNotPopulatedError instead of looping
    (deleting the retry `return bundle`) turns this back into a 503.
    """
    bed.set_wait(5.0)  # generous: the script, not the clock, ends this test

    resp, calls, elapsed = bed.run(_populating, _populating, _ready)

    assert resp.status_code == 200, resp.text
    assert resp.json()["hash"] == "cloned-head"
    assert len(calls) == 3, f"expected 2 failed polls then a hit, got {len(calls)}"
    assert sleeps, "the route returned 200 without ever waiting"
    assert elapsed < bed.wait, "the route waited out the whole budget after success"
    assert _wait_outcomes(emitted) == ["served"], (
        "a served wait must be counted exactly once, so a dashboard can "
        f"separate rescued requests from stranded ones: {_wait_outcomes(emitted)}"
    )
    assert not [t for t, _ in emitted["event"] if t == "ScopePolicyUnavailable"], (
        "a request that was served emitted the unavailable event anyway — the "
        "503 rate would read as if nothing had been rescued"
    )


def test_wait_expiry_falls_through_to_the_unchanged_503_contract(bed, emitted, sleeps):
    """When the clone outlives the budget the answer must be exactly what it
    was before this change — same status, same Retry-After, same event.

    Mutation: raising a bare HTTPException at the deadline instead of
    re-raising CloneNotPopulatedError into the existing handler drops the
    Retry-After header and the event, and fails here.
    """
    records = []
    from opal_common.logger import logger

    sink = logger.add(lambda m: records.append(str(m)), level="INFO")
    try:
        resp, calls, elapsed = bed.run(_populating)
    finally:
        logger.remove(sink)

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "30"
    assert len(calls) > 2, f"the route barely polled before giving up: {len(calls)}"

    assert elapsed >= bed.wait * 0.9, f"gave up after {elapsed:.3f}s < {bed.wait}s"
    assert elapsed < bed.wait + 2.0, (
        f"held the request {elapsed:.3f}s against a {bed.wait}s budget — an "
        "unbounded hold is a 504 at the load balancer, not a 503"
    )
    assert (
        sum(sleeps) <= bed.wait
    ), f"slept {sum(sleeps):.3f}s in total against a {bed.wait}s budget"

    assert _wait_outcomes(emitted) == ["timeout"], _wait_outcomes(emitted)
    assert (
        "ScopePolicyUnavailable",
        {
            "scope_id": "live",
            "status": "503",
            "retryable": "true",
        },
    ) in emitted["event"], emitted["event"]

    waited_lines = [r for r in records if "after waiting" in r]
    assert waited_lines, (
        "the 503 log does not say how long the request was held, so an "
        f"operator cannot tell a tuned wait from an ignored one: {records}"
    )


def test_the_final_poll_is_clamped_to_what_is_left_of_the_budget(bed, sleeps):
    """The hold ends at the deadline, not at the next poll boundary.

    Unclamped, the last sleep runs a full interval past the deadline — up to a
    second in production. Small, but it means the effective bound is the poll
    interval rather than the number the operator set, and the number they set
    is chosen against a load-balancer timeout.

    Configured with a wait that is NOT a whole number of polls, which is the
    only shape that can tell the two apart (the timeout test above uses an
    exact multiple, so it cannot).

    Mutation: `asyncio.sleep(_CLONE_WAIT_POLL_SECONDS)` in place of
    `asyncio.sleep(min(_CLONE_WAIT_POLL_SECONDS, remaining))` fails here.
    """
    bed.set_poll(0.1)
    bed.set_wait(0.15)

    resp, _, _ = bed.run(_populating)

    assert resp.status_code == 503
    assert len(sleeps) >= 2, f"only {len(sleeps)} polls — the clamp never applied"
    assert sum(sleeps) <= bed.wait, (
        f"slept {sum(sleeps):.3f}s against a {bed.wait}s budget: the last poll "
        "runs to its own boundary, so the poll interval sets the real bound"
    )


def test_a_retried_attempt_reaches_the_same_handler_as_the_first(bed, emitted):
    """A clone can finish and still fail to build a bundle. Whatever the
    retried attempt raises must be classified by the handlers the first attempt
    would have hit — not collapsed into the 503 the wait was about.

    Mutation: wrapping the retry in `except Exception: raise
    CloneNotPopulatedError` (or catching the retry inside the wait loop)
    turns the 409 into a 503 and fails here.
    """
    bed.set_wait(5.0)

    resp, calls, _ = bed.run(_populating, _wrong_branch)

    assert resp.status_code == 409, (
        "a branch that does not exist stayed retryable because it surfaced "
        "during the wait — the PDP would retry a permanent misconfiguration"
    )
    assert "retry-after" not in {k.lower() for k in resp.headers}
    assert len(calls) == 2


def test_a_transient_fault_during_the_wait_keeps_its_own_retry_after(bed):
    """Same seam, the other direction: the broad transient tuple must still
    answer 503 + Retry-After 5, not the clone-in-progress hint of 30.

    Mutation: re-raising the retry's exception as the original
    CloneNotPopulatedError answers Retry-After 30 and fails here.
    """
    bed.set_wait(5.0)

    resp, calls, _ = bed.run(_populating, _object_store_broken)

    assert resp.status_code == 503
    assert (
        resp.headers["retry-after"] == "5"
    ), "a gutted object store was reported with the clone-in-progress hint"
    assert len(calls) == 2


def test_no_wait_when_the_first_attempt_is_not_a_clone_in_progress(
    bed, emitted, sleeps
):
    """Only an unpopulated clone is worth waiting for. Holding a request open
    for a fault that will not resolve on its own burns a worker slot and delays
    the client's own recovery.

    Mutation: widening the caught type to ValueError/Exception around the
    first attempt makes this request wait, and both assertions below fail.
    """
    resp, calls, elapsed = bed.run(_clone_dir_gone)

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"
    assert len(calls) == 1, f"a non-retryable-by-waiting fault was polled: {calls}"
    assert not sleeps, f"the route waited for a fault waiting cannot fix: {sleeps}"
    assert not _wait_outcomes(emitted), "counted a wait that never happened"
    assert elapsed < bed.wait, "the route held the request anyway"


def test_the_wait_does_not_block_the_event_loop(bed, monkeypatch, tmp_path):
    """The hold must be an awaited sleep, not a blocking one: a worker holds
    many of these at once, and gunicorn kills a worker whose heartbeat stops.

    Asserts the loop keeps running by scheduling an independent coroutine
    while the route is waiting. Mutation: swapping `await asyncio.sleep(...)`
    for `time.sleep(...)` starves the ticker and fails here.
    """
    ticks = []

    async def ticker():
        for _ in range(50):
            await asyncio.sleep(0.005)
            ticks.append(1)

    bed.set_wait(0.2)

    fake, calls = _scripted_make_bundle(_populating)
    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)

    app = FastAPI()
    repo = FakeScopeRepository([_scope()])
    service = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), None, service), prefix="/scopes"
    )

    @app.get("/tick")
    async def _start_ticker():
        asyncio.create_task(ticker())
        return {}

    with TestClient(app) as client:
        client.get("/tick")
        resp = client.get("/scopes/live/policy")

    assert resp.status_code == 503
    assert len(ticks) > 5, (
        f"the event loop advanced only {len(ticks)} ticks while one request "
        "waited for a clone — the wait is blocking the worker"
    )
