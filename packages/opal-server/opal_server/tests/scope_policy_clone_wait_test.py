"""GET /scopes/:scope_id/policy holds a bounded wait while the clone is being
populated, instead of answering 503 the instant it finds an empty clone.

The 503 is honest but useless to the caller that matters: opal-client 0.9.6
ignores Retry-After. It makes five attempts with random-exponential backoff
capped at 10s (~20-40s of coverage) and then goes quiet until the next pub/sub
policy message or a reconnect. A clone that outlives those attempts leaves the
PDP with no policy and nothing scheduled to fix it — and the update-all
notification published when the clone finishes only names the scope that was
syncing, so siblings sharing that clone get nothing.

Holding the request turns that gap into latency the client already tolerates.
What makes it safe at fleet scale is the other half: the hold is capped per
process, clamped, released on disconnect, and every request that enters it is
accounted for exactly once. Every test below names the single-line mutation it
catches.
"""
import asyncio
import math
import re
import time
from pathlib import Path

import httpx
import pygit2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from git import NoSuchPathError
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server import config as server_config_module
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    BranchHeadNotFoundError,
    CloneNotPopulatedError,
    GitPolicyFetcher,
)
from opal_server.scopes import api as scopes_api
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService
from starlette.requests import Request

_WAIT_METRIC = "opal_server.scopes.policy_clone_wait"
_INFLIGHT_METRIC = "opal_server.scopes.policy_clone_wait_inflight"
_WAITED_METRIC = "opal_server.scopes.policy_clone_wait_seconds"


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


def _app(repo, base_dir):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=None)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), None, service),
        prefix="/scopes",
    )
    return app


def _client(repo, base_dir):
    return TestClient(_app(repo, base_dir))


def _fetcher(base_dir, scope_id="live"):
    return GitPolicyFetcher(Path(base_dir), scope_id, _scope(scope_id).policy)


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
    calls — one entry per attempt, holding the base_hash that attempt
    was given — so a test can assert both how many attempts the route
    made and what it passed.
    """
    calls = []

    def fake_make_bundle(self, base_hash=None):
        calls.append(base_hash)
        return outcomes[min(len(calls) - 1, len(outcomes) - 1)]()

    return fake_make_bundle, calls


def _gated_make_bundle(gate):
    """make_bundle that reports "still cloning" until `gate` flips to True.

    Unlike a scripted one, this is keyed on the CLONE's state rather
    than on an attempt count, so concurrent requests polling the same
    clone all see the same thing — which is what a shared clone actually
    looks like.
    """
    calls = []

    def fake_make_bundle(self, base_hash=None):
        calls.append(base_hash)
        if not gate["ready"]:
            _populating()
        return _ready()

    return fake_make_bundle, calls


@pytest.fixture(autouse=True)
def clean_module_state(monkeypatch):
    """Per-process wait state, reset per test.

    The in-flight count is a module global by design (mutated only on
    the event loop, so it needs no lock). A test that leaked a non-zero
    count would silently shed in the next one.
    """
    monkeypatch.setattr(scopes_api, "_clone_wait_inflight", 0)
    monkeypatch.setattr(scopes_api, "_clone_wait_clamp_logged", False)
    yield
    assert (
        scopes_api._clone_wait_inflight == 0
    ), "a wait slot was never released — the try/finally around the loop leaks"


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
        poll = 0.02

        def __init__(self):
            self.set_wait(self.wait)
            self.set_poll(self.poll)

        def set_wait(self, seconds):
            self.wait = seconds
            monkeypatch.setattr(
                opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", seconds
            )

        def set_poll(self, seconds):
            self.poll = seconds
            monkeypatch.setattr(
                "opal_server.scopes.api._CLONE_WAIT_POLL_SECONDS", seconds
            )

        def set_cap(self, requests):
            monkeypatch.setattr(
                opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", requests
            )

        def install(self, *outcomes):
            fake, calls = _scripted_make_bundle(*outcomes)
            monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
            return calls

        def app(self, *scopes):
            return _app(FakeScopeRepository(list(scopes) or [_scope()]), tmp_path)

        def run(self, *outcomes, scope_id="live", url="", scopes=None):
            calls = self.install(*outcomes)
            client = TestClient(self.app(*(scopes or [_scope(scope_id)])))
            started = time.monotonic()
            resp = client.get(url or f"/scopes/{scope_id}/policy")
            return resp, calls, time.monotonic() - started

    return Bed()


@pytest.fixture
def emitted(monkeypatch):
    """Capture the metrics facade, patched on the module object: every emitter
    does `from opal_common.monitoring import metrics`, so they share it."""
    calls = {"increment": [], "event": [], "gauge": []}
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
    monkeypatch.setattr(
        metrics,
        "gauge",
        lambda metric, value, tags=None: calls["gauge"].append((metric, value, tags)),
    )
    return calls


def _wait_outcomes(emitted):
    return [
        (tags or {}).get("outcome")
        for metric, tags in emitted["increment"]
        if metric == _WAIT_METRIC
    ]


def _gauged(emitted, name):
    return [(value, tags) for metric, value, tags in emitted["gauge"] if metric == name]


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


@pytest.fixture
def logs():
    records = []
    sink = logger.add(lambda m: records.append(str(m)), level="INFO")
    yield records
    logger.remove(sink)


def _waited_in(records, needle):
    """The `{waited:.1f}s` figure out of a log line, as a float."""
    lines = [r for r in records if needle in r]
    assert lines, f"no log line containing {needle!r}: {records}"
    found = re.search(r"([0-9]+\.[0-9]+)s", lines[-1])
    assert found, f"log line states no duration: {lines[-1]!r}"
    return float(found.group(1))


# --- the budget: disabled, invalid, clamped ------------------------------


def test_wait_disabled_answers_503_after_a_single_attempt(bed, emitted, sleeps):
    """0 must mean exactly the pre-wait behaviour, as an escape hatch that is
    worth having only if it is truly identical.

    Mutation: dropping the `if wait <= 0: raise` guard leaves the deadline
    already expired, so the route still makes ONE attempt and still 503s —
    what gives it away is the accounting, since a request that never waited
    would be counted as a timeout. That is the assertion that fires.
    """
    bed.set_wait(0)

    resp, calls, _ = bed.run(_populating)

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "30"
    assert len(calls) == 1, f"wait=0 still retried make_bundle: {len(calls)} attempts"
    assert not sleeps, f"wait=0 still slept: {sleeps}"
    assert not _wait_outcomes(emitted), (
        "a request that never waited was counted as one that did — the "
        f"wait dashboard would show traffic on a disabled feature: "
        f"{_wait_outcomes(emitted)}"
    )


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), float("-inf"), -1.0, 0.0, None, "twenty"]
)
def test_a_budget_that_is_not_a_positive_finite_number_is_refused(bed, bad):
    """Asserted directly on the guard, because end-to-end cannot see it fast.

    `inf` is the detector for `math.isfinite`, not `nan`: since the deadline
    loop was made NaN-safe, a NaN budget breaks on the first iteration and
    looks exactly like a disabled wait from outside. `inf`, dropped through the
    same hole, sails past `wait <= 0`, gets clamped, and holds every
    clone-in-progress request for the full 55s ceiling — correct-looking, and
    only visible end-to-end by waiting 55 seconds for it.

    A non-numeric value never reaches this function in production (Confi parses
    the environment at import, so the process fails at startup); it is asserted
    here because the guard also covers a value assigned at runtime.

    Mutation: dropping `math.isfinite` returns 55.0 for inf and nan for nan,
    and both fail here in milliseconds.
    """
    bed.set_wait(bad)

    assert scopes_api._bounded_clone_wait() == 0.0


@pytest.mark.parametrize("bad", [-1.0, None, "twenty"])
def test_a_refused_budget_answers_503_after_a_single_attempt(bed, sleeps, bad):
    """The same refusal seen from the route, on the params that are cheap to
    drive end-to-end (nan and inf are covered by the direct assertion above —
    inf would cost this test 55 seconds of real hold).

    Mutation: dropping the `if wait <= 0: raise` guard makes the route enter
    the wait with a zero budget, which the accounting then counts.
    """
    bed.set_wait(bad)

    resp, calls, _ = bed.run(_populating)

    assert resp.status_code == 503
    assert len(calls) == 1, f"a {bad} budget was treated as a real one"
    assert not sleeps


@pytest.mark.asyncio
async def test_the_deadline_loop_cannot_spin_even_if_a_nan_budget_reaches_it(
    tmp_path, monkeypatch, emitted
):
    """Defence in depth for the one value that turns a bounded loop unbounded.

    `_bounded_clone_wait` refuses a NaN budget, so in the shipped code this
    cannot happen — which is exactly why it is worth pinning separately. NaN
    compares False against BOTH `<= 0` and `> 0`, so a loop written
    `if remaining <= 0: break` does not terminate on a NaN deadline: it polls
    for the life of the process while holding one of the capped slots. That is
    a worse failure than the one the budget guard prevents, and it depends on a
    check three frames away staying correct.

    Hands the loop a NaN budget directly, past that guard.

    Driven through an ASGI client under `asyncio.wait_for` rather than the
    TestClient: this repo configures no pytest timeout, so a regression here
    would otherwise hang the suite indefinitely instead of failing. The
    deadline below turns that into an ordinary red test.

    Mutation: `if remaining <= 0:` in place of `if not (remaining > 0):` never
    returns, and the wait_for fails this test.
    """
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    monkeypatch.setattr("opal_server.scopes.api._CLONE_WAIT_POLL_SECONDS", 0.02)
    monkeypatch.setattr(
        "opal_server.scopes.api._bounded_clone_wait", lambda: float("nan")
    )
    fake, calls = _scripted_make_bundle(_populating)
    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)

    transport = httpx.ASGITransport(app=_app(FakeScopeRepository([_scope()]), tmp_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:
        try:
            resp = await asyncio.wait_for(client.get("/scopes/live/policy"), 2.0)
        except asyncio.TimeoutError:
            pytest.fail(
                "the deadline loop never terminated on a NaN budget: the "
                "request polls forever, holding a capped slot for the life of "
                "the process"
            )

    assert resp.status_code == 503
    assert len(calls) == 1, f"a NaN deadline was polled against: {len(calls)}"
    assert _wait_outcomes(emitted) == ["timeout"], _wait_outcomes(emitted)


def test_an_oversized_wait_is_clamped_below_the_load_balancer_timeout(
    logs, monkeypatch
):
    """A hold longer than the ALB idle timeout produces the 504 the hold exists
    to prevent, so the ceiling is enforced in code, not just in prose.

    Also pins that the WARNING latches: a per-request warning on a
    misconfigured fleet is thousands of identical lines a minute.

    Mutation: dropping the `min(wait, _CLONE_WAIT_MAX_SECONDS)` clamp returns
    the raw 3600 and fails the first assertion.
    """
    assert scopes_api._CLONE_WAIT_MAX_SECONDS < 60.0, (
        "the clamp is at or above the 60s ALB idle timeout, so a clamped hold "
        "can still be cut off as a 504"
    )

    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 3600.0)
    assert scopes_api._bounded_clone_wait() == scopes_api._CLONE_WAIT_MAX_SECONDS
    assert scopes_api._bounded_clone_wait() == scopes_api._CLONE_WAIT_MAX_SECONDS

    clamps = [r for r in logs if "clamp" in r.lower()]
    assert len(clamps) == 1, (
        f"expected exactly one clamp warning per process, got {len(clamps)} — "
        "a misconfigured fleet would emit one per request"
    )


def test_an_ordinary_wait_is_returned_unchanged(bed):
    """The clamp must not quietly reshape a normal budget."""
    bed.set_wait(7.5)
    assert scopes_api._bounded_clone_wait() == 7.5


def _MDX_TEXT():
    return (
        Path(server_config_module.__file__).parents[3]
        / "documentation"
        / "docs"
        / "getting-started"
        / "configuration.mdx"
    ).read_text()


def test_the_poll_interval_matches_what_the_docs_promise():
    """The published description tells operators the route re-checks "once a
    second". Nothing but this test couples that sentence to the constant, and
    the constant is not a config key precisely so the docs are its contract.

    Takes no `bed`: that fixture tunes the poll down to test timescales, which
    is exactly the value this test must not see.

    Mutation: changing _CLONE_WAIT_POLL_SECONDS without touching the docs
    fails here.
    """
    assert scopes_api._CLONE_WAIT_POLL_SECONDS == 1.0

    # Adjacent string literals wrapped across source lines are joined first:
    # black splits the description mid-sentence, so the phrase exists in the
    # value but not in the raw bytes.
    config_py = re.sub(
        r'"\s*\n\s*"', "", Path(server_config_module.__file__).read_text()
    )
    for name, text in (("config.py", config_py), ("configuration.mdx", _MDX_TEXT())):
        assert "once a second" in text, (
            f"{name} no longer states the poll cadence, so the only "
            "description of _CLONE_WAIT_POLL_SECONDS an operator can read is gone"
        )


# --- the happy path ------------------------------------------------------


def test_the_clamp_ceiling_matches_what_the_docs_promise():
    """`_CLONE_WAIT_MAX_SECONDS` is not a config key, so the published
    description IS its contract: it tells operators values above 55s are
    clamped. Nothing but this test couples that sentence to the constant.

    Takes no `bed` — nothing here may be tuned to test timescales.

    Mutation: changing the constant without touching the docs fails here.
    """
    assert scopes_api._CLONE_WAIT_MAX_SECONDS == 55.0

    config_py = re.sub(
        r'"\s*\n\s*"', "", Path(server_config_module.__file__).read_text()
    )
    for name, text in (("config.py", config_py), ("configuration.mdx", _MDX_TEXT())):
        assert "55s" in text, (
            f"{name} no longer states the clamp ceiling, so the only "
            "description of _CLONE_WAIT_MAX_SECONDS an operator can read is gone"
        )


def test_clone_that_finishes_mid_wait_is_served_instead_of_503(
    bed, emitted, sleeps, logs
):
    """The whole point: a clone that completes inside the budget produces a
    200, not a 503 the client will not act on.

    Mutation: returning the first CloneNotPopulatedError instead of looping
    (deleting the retry's `return bundle`) turns this back into a 503.
    Deleting the "became available" INFO line fails the log assertion — that
    line is how an operator sees the wait working at all, since a served wait
    is otherwise indistinguishable from a request that never waited.
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
    assert _waited_in(logs, "became available") >= 0.0
    served = [
        value
        for value, tags in _gauged(emitted, _WAITED_METRIC)
        if (tags or {}).get("outcome") == "served"
    ]
    assert len(served) == 1 and served[0] > 0, (
        "the hold duration is not published for served requests, so the knob "
        f"cannot be tuned against what it actually saved: {served}"
    )


def test_every_poll_re_sends_the_clients_base_hash(bed):
    """A diff bundle is built against the hash the client already has. Dropping
    it on a retry silently upgrades that client to a FULL bundle — correct
    output, many times the payload, on every request the wait rescues.

    Mutation: `run_sync(fetcher.make_bundle)` (or passing None) in the retry
    fails here.
    """
    bed.set_wait(5.0)

    resp, calls, _ = bed.run(
        _populating,
        _populating,
        _ready,
        url="/scopes/live/policy?base_hash=abc123",
    )

    assert resp.status_code == 200
    assert calls == [
        "abc123",
        "abc123",
        "abc123",
    ], f"the client's base_hash was not preserved across polls: {calls}"


def test_a_request_without_a_base_hash_keeps_sending_none(bed):
    """The other half of the same claim, so a retry cannot invent a hash."""
    bed.set_wait(5.0)

    resp, calls, _ = bed.run(_populating, _populating, _ready)

    assert resp.status_code == 200
    assert calls == [None, None, None], calls


# --- expiry --------------------------------------------------------------


def test_wait_expiry_falls_through_to_the_unchanged_503_contract(
    bed, emitted, sleeps, logs
):
    """When the clone outlives the budget the answer must be exactly what it
    was before this change — same status, same Retry-After, same event.

    Mutation: raising a bare HTTPException at the deadline instead of
    re-raising CloneNotPopulatedError into the existing handler drops the
    Retry-After header and the event, and fails here. Dropping the sleep (a
    spin loop) blows the poll-count bound.
    """
    resp, calls, elapsed = bed.run(_populating)

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "30"
    assert len(calls) > 2, f"the route barely polled before giving up: {len(calls)}"
    assert len(calls) <= bed.wait / bed.poll + 2, (
        f"{len(calls)} attempts for a {bed.wait}s budget at a {bed.poll}s poll: "
        "the route is spinning, not sleeping, between checks"
    )

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
        {"scope_id": "live", "status": "503", "retryable": "true"},
    ) in emitted["event"], emitted["event"]

    # The number itself, not merely the presence of a number: a hardcoded 0.0
    # (or a `getattr(exc, ..., 0.0)` that silently defaults) reads as "we did
    # not wait" on exactly the requests that waited longest.
    waited = _waited_in(logs, "after waiting")
    assert (
        waited >= bed.wait * 0.9
    ), f"the 503 log reports {waited}s for a request held {elapsed:.3f}s"
    timed_out = [
        value
        for value, tags in _gauged(emitted, _WAITED_METRIC)
        if (tags or {}).get("outcome") == "timeout"
    ]
    assert len(timed_out) == 1 and timed_out[0] >= bed.wait * 0.9, timed_out


def test_the_final_poll_is_clamped_to_what_is_left_of_the_budget(bed, sleeps):
    """The hold ends at the deadline, not at the next poll boundary.

    Unclamped, the last sleep runs a full interval past the deadline — up to a
    second in production. Small, but it means the effective bound is the poll
    interval rather than the number the operator set, and the number they set
    is chosen against a load-balancer timeout.

    Configured with a wait that is NOT a whole number of polls, which is the
    only shape that can tell the two apart (the expiry test above uses an
    exact multiple, so it cannot).

    Mutation: `asyncio.sleep(_CLONE_WAIT_POLL_SECONDS)` in place of
    `asyncio.sleep(min(_CLONE_WAIT_POLL_SECONDS, remaining))` fails here.
    """
    bed.set_poll(0.1)
    bed.set_wait(0.15)

    resp, _, elapsed = bed.run(_populating)

    assert resp.status_code == 503
    assert len(sleeps) >= 2, f"only {len(sleeps)} polls — the clamp never applied"
    assert sum(sleeps) <= bed.wait, (
        f"slept {sum(sleeps):.3f}s against a {bed.wait}s budget: the last poll "
        "runs to its own boundary, so the poll interval sets the real bound"
    )
    assert elapsed <= bed.wait * 3 + 0.1, (
        f"the request was held {elapsed:.3f}s of wall clock against a "
        f"{bed.wait}s budget — what the operator set is not what they get"
    )


# --- what must NOT be waited on ------------------------------------------


@pytest.mark.parametrize(
    "first_failure, retry_after",
    [
        (_clone_dir_gone, "5"),
        # BranchHeadNotFoundError subclasses ValueError, as does
        # CloneNotPopulatedError. Widening the caught type by one level
        # therefore swallows a PERMANENT misconfiguration into the wait.
        (_wrong_branch, None),
        (_object_store_broken, "5"),
    ],
)
def test_no_wait_when_the_first_attempt_is_not_a_clone_in_progress(
    bed, emitted, sleeps, first_failure, retry_after
):
    """Only an unpopulated clone is worth waiting for. Holding a request open
    for a fault that will not resolve on its own burns a held slot (there are
    only so many) and delays the client's own recovery.

    Mutation: widening the caught type to ValueError or Exception around the
    first attempt makes these requests wait, and both assertions below fail.
    """
    resp, calls, elapsed = bed.run(first_failure)

    assert resp.status_code == (409 if retry_after is None else 503)
    if retry_after is None:
        assert "retry-after" not in {k.lower() for k in resp.headers}
    else:
        assert resp.headers["retry-after"] == retry_after
    assert len(calls) == 1, f"a fault that waiting cannot fix was polled: {calls}"
    assert not sleeps, f"the route waited for a fault waiting cannot fix: {sleeps}"
    assert not _wait_outcomes(emitted), "counted a wait that never happened"
    assert elapsed < bed.wait, "the route held the request anyway"


# --- what a retried attempt is allowed to do -----------------------------


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
    assert _wait_outcomes(emitted) == ["error"], (
        "a wait that ended in an unexpected exception was not accounted for; "
        f"held slots would appear to vanish from the dashboard: "
        f"{_wait_outcomes(emitted)}"
    )


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


# --- the cost of holding -------------------------------------------------


def test_the_wait_does_not_block_the_event_loop(bed, monkeypatch, tmp_path):
    """The hold must be an awaited sleep, not a blocking one: a worker holds
    many of these at once, and gunicorn kills a worker whose heartbeat stops.

    Asserts the loop keeps running by scheduling an independent coroutine
    while the route is waiting. The threshold has to sit in the GAP, not just
    above zero: a blocked loop still yields at every executor round-trip, so
    ~10 ticks get through even with a blocking sleep, and an earlier `> 5`
    version of this test passed with `time.sleep` in place. A free loop
    manages ~40 over the same 0.2s budget.

    Mutation: swapping `await asyncio.sleep(...)` for `time.sleep(...)` drops
    the tick count into single digits and fails here.
    """
    ticks = []

    async def ticker():
        for _ in range(50):
            await asyncio.sleep(0.005)
            ticks.append(1)

    bed.set_wait(0.2)
    bed.install(_populating)
    app = bed.app()

    @app.get("/tick")
    async def _start_ticker():
        asyncio.create_task(ticker())
        return {}

    with TestClient(app) as client:
        client.get("/tick")
        resp = client.get("/scopes/live/policy")

    assert resp.status_code == 503
    assert len(ticks) >= 20, (
        f"the event loop advanced only {len(ticks)} ticks while one request "
        "waited for a clone (a free loop manages ~40 in that budget) — the "
        "wait is blocking the worker between polls"
    )


@pytest.mark.asyncio
async def test_the_cap_sheds_the_excess_instead_of_holding_every_request(
    tmp_path, monkeypatch, emitted
):
    """Polling is cheap; RELEASING is not. When the clone lands, every held
    request builds a full bundle on the same ~min(32, cpu+4)-thread executor,
    whose measured throughput falls from ~52 bundles/s at 32 concurrent to
    ~18/s at 1000. Unbounded, a pod holding thousands of PDPs turns the hold
    into a queue that outlives the 60s ALB idle timeout — the 504 this feature
    exists to prevent — and a rolling restart SIGKILLs the worker at 30s with
    those connections still open.

    So the hold is capped per process, and the excess gets exactly what it
    would have got before the wait existed: an immediate 503 + Retry-After 30.

    Mutation: dropping the cap check serves all 5 (no shed count) and fails.
    Dropping the try/finally decrement leaves the gauge above 0 at the end.
    """
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 5.0)
    monkeypatch.setattr("opal_server.scopes.api._CLONE_WAIT_POLL_SECONDS", 0.02)
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 3)

    gate = {"ready": False}
    fake, _calls = _gated_make_bundle(gate)
    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
    app = _app(FakeScopeRepository([_scope()]), tmp_path)

    asyncio.get_running_loop().call_later(0.15, gate.__setitem__, "ready", True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:
        responses = await asyncio.gather(
            *(client.get("/scopes/live/policy") for _ in range(5))
        )

    codes = sorted(r.status_code for r in responses)
    assert codes == [
        200,
        200,
        200,
        503,
        503,
    ], f"a cap of 3 did not shed the other 2: {codes}"
    for shed in [r for r in responses if r.status_code == 503]:
        assert (
            shed.headers["retry-after"] == "30"
        ), "a shed request got something other than the pre-wait answer"

    outcomes = sorted(_wait_outcomes(emitted))
    assert outcomes == [
        "served",
        "served",
        "served",
        "shed",
        "shed",
    ], f"every request that reached the wait is counted exactly once: {outcomes}"

    readings = _gauged(emitted, _INFLIGHT_METRIC)
    assert readings, "the held-request count is not published at all"
    assert (
        max(value for value, _ in readings) == 3
    ), f"the gauge never reflected a full cap: {[v for v, _ in readings]}"
    assert readings[-1][0] == 0, (
        f"the gauge ended at {readings[-1][0]} — a leaked slot permanently "
        "lowers the cap for this worker"
    )
    assert "pid" in (readings[-1][1] or {}), (
        "the gauge is untagged, so a pod's workers collapse into one "
        "last-write-wins series and the cap looks unreached"
    )
    # Deliberately NOT tagged by scope_id/source_id: this is a per-process
    # resource, and a per-scope tag would be unbounded cardinality.
    assert set(readings[-1][1]) == {"pid"}, readings[-1][1]


@pytest.mark.asyncio
async def test_a_cap_of_zero_means_no_cap(tmp_path, monkeypatch, emitted):
    """The documented escape hatch, which is only worth documenting if it
    works: an operator who has measured their own executor and wants the old
    unbounded behaviour sets 0.

    Mutation: `if cap <= _clone_wait_inflight` in place of
    `if 0 < cap <= _clone_wait_inflight` sheds EVERY request at cap=0 (0 <= 0),
    turning the escape hatch into "never wait at all" — the exact inversion of
    what the description promises. Fails here.
    """
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 5.0)
    monkeypatch.setattr("opal_server.scopes.api._CLONE_WAIT_POLL_SECONDS", 0.02)
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 0)

    gate = {"ready": False}
    fake, _calls = _gated_make_bundle(gate)
    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)
    app = _app(FakeScopeRepository([_scope()]), tmp_path)
    asyncio.get_running_loop().call_later(0.15, gate.__setitem__, "ready", True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:
        responses = await asyncio.gather(
            *(client.get("/scopes/live/policy") for _ in range(4))
        )

    assert [r.status_code for r in responses] == [
        200
    ] * 4, f"cap=0 shed requests: {[r.status_code for r in responses]}"
    assert _wait_outcomes(emitted) == ["served"] * 4
    assert (
        max(value for value, _ in _gauged(emitted, _INFLIGHT_METRIC)) == 4
    ), "cap=0 did not actually hold them concurrently"


def test_a_metrics_sink_that_raises_cannot_leak_a_held_slot(bed, monkeypatch):
    """The in-flight count is the cap. A slot lost to a telemetry failure is
    never returned, so the worker's effective cap drops by one per occurrence
    until it stops waiting for anything.

    The request itself fails loudly here (the raising gauge propagates, and
    nothing in the route catches RuntimeError) — that is the pre-existing
    contract for a broken sink and not what this test is about. What it pins
    is that the SLOT comes back regardless.

    Mutation: publishing the gauge before the `try` (its previous position)
    leaks the slot and fails here.
    """

    def exploding_gauge(metric, value, tags=None):
        raise RuntimeError("statsd is on fire")

    monkeypatch.setattr(metrics, "gauge", exploding_gauge)

    with pytest.raises(RuntimeError):
        bed.run(_populating)

    assert scopes_api._clone_wait_inflight == 0, (
        "the wait slot was lost to a metrics failure: this worker now holds "
        "one fewer request forever"
    )


@pytest.mark.asyncio
async def test_a_disconnected_client_stops_being_waited_for(
    tmp_path, monkeypatch, emitted
):
    """A PDP that has already given up (or a load balancer that cut the
    connection) is still holding a capped slot and will still trigger a full
    bundle build on release — for a response nobody will read.

    The check runs against the REAL Starlette Request, so this also pins that
    the route hands one to the wait: with no request threaded through, the
    fake below is never consulted, the wait runs to expiry, and the outcome is
    `timeout` rather than `disconnected`.

    Mutation: removing the `is_disconnected` check runs to the deadline and
    fails on both the outcome and the poll count.
    """
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 5.0)
    monkeypatch.setattr("opal_server.scopes.api._CLONE_WAIT_POLL_SECONDS", 0.02)

    polls = {"n": 0}

    async def hung_up_after_two_polls(self):
        polls["n"] += 1
        return polls["n"] > 2

    monkeypatch.setattr(Request, "is_disconnected", hung_up_after_two_polls)
    calls = []

    def never_populated(self, base_hash=None):
        calls.append(base_hash)
        _populating()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", never_populated)

    transport = httpx.ASGITransport(app=_app(FakeScopeRepository([_scope()]), tmp_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://bed") as client:
        started = time.monotonic()
        resp = await client.get("/scopes/live/policy")
        elapsed = time.monotonic() - started

    assert resp.status_code == 503
    assert _wait_outcomes(emitted) == ["disconnected"], _wait_outcomes(emitted)
    assert (
        elapsed < 1.0
    ), f"kept waiting {elapsed:.3f}s for a client that had hung up (budget 5s)"
    assert len(calls) <= 4, (
        f"{len(calls)} bundle attempts after the client disconnected: the "
        "check does not stop the loop"
    )
    # The 503 is shaped for a socket nobody is reading. Emitting the
    # unavailable event for it inflates the rate an operator watches to decide
    # whether CLIENTS are being served, with responses no client will see.
    #
    # Mutation: dropping the `if not exc.client_disconnected` guard around the
    # log and the event in the route fails here.
    assert not [
        t for t, _ in emitted["event"] if t == "ScopePolicyUnavailable"
    ], f"a client that had hung up still produced a 503 event: {emitted['event']}"


@pytest.mark.asyncio
async def test_a_cancelled_request_releases_its_slot_and_is_counted(
    tmp_path, monkeypatch, emitted
):
    """Cancellation is the normal way a server-side wait ends when the ASGI
    server tears a connection down. It must not leak the capped slot, and it
    must be visible: a fleet whose waits are all being cancelled looks
    identical to one where nothing is waiting.

    Mutation: dropping the `except asyncio.CancelledError` arm leaves the
    outcome as `error` (cancellation is a BaseException, so no `except
    Exception` sees it) and fails here. Dropping the finally leaks the slot,
    which the autouse fixture catches.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 5.0)
    monkeypatch.setattr("opal_server.scopes.api._CLONE_WAIT_POLL_SECONDS", 0.01)
    fake, _calls = _scripted_make_bundle(_populating)
    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake)

    task = asyncio.create_task(
        scopes_api._make_bundle_waiting_for_clone(
            _fetcher(tmp_path), None, "live", None
        )
    )
    await asyncio.sleep(0.05)
    assert scopes_api._clone_wait_inflight == 1, "the request never took a slot"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _wait_outcomes(emitted) == ["cancelled"], _wait_outcomes(emitted)
    assert _gauged(emitted, _INFLIGHT_METRIC)[-1][0] == 0


# --- the default-scope path ----------------------------------------------


def test_the_default_scope_bundle_waits_for_its_own_clone(bed, emitted):
    """An unknown scope is served from the `default` scope's clone, and that
    clone is populated by the same recovery as any other. Before this, the
    default path was the one place a mid-clone request still got an immediate
    503 — and it is the path every PDP with a stale scope id takes.

    Mutation: reverting `_generate_default_scope_bundle` to a bare
    `run_sync(fetcher.make_bundle, None)` answers 503 and fails here.
    """
    bed.set_wait(5.0)

    resp, calls, _ = bed.run(
        _populating,
        _populating,
        _ready,
        scope_id="ghost",
        scopes=[_scope("default")],
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["hash"] == "cloned-head"
    assert len(calls) == 3
    assert _wait_outcomes(emitted) == ["served"]


def test_the_default_scope_keeps_its_own_503_contract_on_expiry(bed, emitted, logs):
    """Falling through must land in the default path's OWN handler, which
    answers Retry-After 5 — not the primary path's 30. Same wait, two
    contracts, because the two paths make different promises about what the
    caller should do next.

    That handler must also report the hold. Without an arm of its own this
    exception is swallowed by the broad transient tuple below it
    (CloneNotPopulatedError subclasses ValueError), which produces the
    identical status and header and a log line indistinguishable from a 503
    nothing ever waited for — on the branch every PDP with a stale scope id
    takes.

    Mutation: raising an HTTPException with the clone-in-progress Retry-After
    from inside the wait (instead of re-raising into each caller's handler)
    answers 30 here; deleting the dedicated `except CloneNotPopulatedError`
    arm from `_generate_default_scope_bundle` drops the hold from the log.
    Both fail here.
    """
    resp, _calls, _ = bed.run(_populating, scope_id="ghost", scopes=[_scope("default")])

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"
    assert _wait_outcomes(emitted) == ["timeout"]
    assert (
        _waited_in(logs, "Default-scope bundle") >= bed.wait * 0.9
    ), "the default path's 503 does not say how long it held the request"


def test_the_wait_is_declared_on_the_exception_not_smuggled(bed, logs):
    """The hold is reported off an attribute of the raised error. Declaring it
    on the class (with a 0.0 default) rather than relying on a getattr default
    at the read site is what makes a missing assignment a visible 0.0 in ONE
    place instead of a silent default at every reader.

    Mutation: deleting `waited_seconds` from CloneNotPopulatedError raises
    AttributeError in the route (500) and fails here.
    """
    assert CloneNotPopulatedError.waited_seconds == 0.0

    resp, _, _ = bed.run(_populating)

    assert resp.status_code == 503
    assert _waited_in(logs, "after waiting") >= bed.wait * 0.9
