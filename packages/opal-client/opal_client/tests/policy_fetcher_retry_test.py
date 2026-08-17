"""Tests for the bundle-fetch retry policy of `opal_client.policy.fetcher`.

The OPAL server (scopes mode) answers `GET /scopes/{id}/policy` with:

  * ``503`` + ``Retry-After: 30``  -- the scope's clone is still in progress
  * ``503`` + ``Retry-After: 5``   -- the clone vanished / is corrupt
  * ``409``                        -- the branch could not be resolved (never
                                      fixes itself by retrying)
  * ``404``                        -- the requested path is not in the repo

Before this module existed the client retried *every* exception with a blind
random-exponential backoff, never read ``Retry-After``, and hammered a 409 four
extra times. These tests pin the classification, the wait computation and the
"do not retry what cannot succeed" rule.

Every test names the single-line mutation it is designed to catch, so that a
future refactor that silently drops a guard fails here.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import aiohttp
import pytest
from fastapi import HTTPException
from tenacity import RetryCallState, wait_fixed
from tenacity.stop import stop_after_attempt, stop_after_delay, stop_any

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.policy.fetcher import (
    BundlePathNotFoundError,
    NonRetryableBundleError,
    PolicyFetcher,
    RetryableBundleError,
    parse_retry_after,
    wait_retry_after_or_backoff,
)
from opal_client.policy.options import ConnRetryOptions

# ---------------------------------------------------------------------------
# aiohttp test doubles
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for `aiohttp.ClientResponse`."""

    def __init__(self, status: int, headers: dict = None, body=None):
        self.status = status
        self.headers = headers or {}
        self._body = body

    async def json(self):
        if self._body is None:
            raise ValueError("no json body")
        return self._body

    async def text(self):
        return str(self._body)


class _FakeGetContext:
    def __init__(self, response_or_exc):
        self._response_or_exc = response_or_exc

    async def __aenter__(self):
        if isinstance(self._response_or_exc, Exception):
            raise self._response_or_exc
        return self._response_or_exc

    async def __aexit__(self, *args):
        return False


class FakeSession:
    """Replaces `aiohttp.ClientSession`; replays a scripted list of responses.

    `_fetch_policy_bundle` opens a fresh session per attempt, so the script
    cursor is class-level: attempt N gets script[N-1]. The last entry repeats if
    more requests arrive than were scripted, so a test can script one response
    and let tenacity retry against it N times.
    """

    instances = []
    script = []
    calls = 0  # class-level: total requests across all attempts

    def __init__(self, *args, **kwargs):
        self.request_kwargs = []
        FakeSession.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, **kwargs):
        FakeSession.calls += 1
        self.request_kwargs.append(kwargs)
        entry = FakeSession.script[
            min(FakeSession.calls - 1, len(FakeSession.script) - 1)
        ]
        return _FakeGetContext(entry)


@pytest.fixture
def scripted_session(monkeypatch):
    """Patch aiohttp.ClientSession with FakeSession for the duration of a test.

    Returns a setter that installs the response script and hands back the list
    of sessions that were created (one per `_fetch_policy_bundle` attempt).
    """
    FakeSession.instances = []
    FakeSession.script = []
    FakeSession.calls = 0
    monkeypatch.setattr(aiohttp, "ClientSession", FakeSession)

    def _install(*responses):
        FakeSession.script = list(responses)
        return FakeSession.instances

    yield _install

    FakeSession.instances = []
    FakeSession.script = []
    FakeSession.calls = 0


def total_requests() -> int:
    """How many HTTP GETs were issued across all attempts."""
    return FakeSession.calls


@pytest.fixture
def no_sleep():
    """Records the waits tenacity *would* have slept, without sleeping."""
    recorded = []

    async def _sleep(seconds):
        recorded.append(seconds)

    _sleep.recorded = recorded
    return _sleep


def make_fetcher(no_sleep=None, attempts: int = None, **config_overrides):
    """Builds a PolicyFetcher, optionally overriding retry knobs."""
    fetcher = PolicyFetcher(backend_url="http://opal-server:7002", token="t")
    if attempts is not None:
        from tenacity import stop_after_attempt

        fetcher._retry_config["stop"] = stop_after_attempt(attempts)
    if no_sleep is not None:
        # `fetch_policy_bundle` builds the tenacity attempter per call from
        # `_retry_config`, so injecting `sleep` here keeps the test instant.
        fetcher._retry_config["sleep"] = no_sleep
    for key, value in config_overrides.items():
        setattr(fetcher, key, value)
    return fetcher


# ---------------------------------------------------------------------------
# parse_retry_after
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header,expected",
    [("30", 30.0), ("5", 5.0), ("0", 0.0), ("0.5", 0.5), ("  12  ", 12.0)],
)
def test_parse_retry_after_delta_seconds(header, expected):
    # MUTATION: returning `None` instead of the parsed float (i.e. deleting the
    # delta-seconds branch) makes every case here fail.
    assert parse_retry_after(header) == pytest.approx(expected)


def test_parse_retry_after_http_date():
    when = datetime.now(timezone.utc) + timedelta(seconds=45)
    parsed = parse_retry_after(format_datetime(when, usegmt=True))
    assert parsed is not None
    # HTTP-date has 1s resolution, and a little wall-clock passes in between.
    # MUTATION: dropping the `parsedate_to_datetime` branch returns None here.
    assert 42.0 <= parsed <= 46.0


def test_parse_retry_after_http_date_in_the_past_is_clamped_to_zero():
    when = datetime.now(timezone.utc) - timedelta(seconds=120)
    # MUTATION: replacing `max(delta, 0.0)` with `delta` yields ~-120 and fails.
    assert parse_retry_after(format_datetime(when, usegmt=True)) == 0.0


def test_parse_retry_after_naive_http_date_is_treated_as_utc():
    # Some servers emit an RFC-850/asctime date with no timezone. `parsedate_to_datetime`
    # returns a naive datetime for those; we must not crash comparing it to an aware now().
    when = datetime.now(timezone.utc) + timedelta(seconds=30)
    naive = when.strftime("%a %b %d %H:%M:%S %Y")  # asctime, no tz
    parsed = parse_retry_after(naive)
    assert parsed is not None
    assert 27.0 <= parsed <= 32.0


@pytest.mark.parametrize(
    "header",
    [None, "", "   ", "soon", "later please", "nan", "inf", "-inf", "1,5", "30s"],
)
def test_parse_retry_after_malformed_is_none(header):
    # MUTATION: removing the `math.isfinite` guard lets "nan"/"inf" through and
    # would produce a NaN/infinite sleep; removing the try/except would raise.
    assert parse_retry_after(header) is None


def test_parse_retry_after_negative_delta_is_clamped_to_zero():
    # MUTATION: `float(value)` without the `max(..., 0.0)` clamp returns -10.0,
    # which tenacity would happily "sleep" for, corrupting the wait computation.
    assert parse_retry_after("-10") == 0.0


# ---------------------------------------------------------------------------
# wait_retry_after_or_backoff
# ---------------------------------------------------------------------------


def _retry_state(exc: Exception = None, attempt_number: int = 2) -> RetryCallState:
    state = RetryCallState(retry_object=None, fn=None, args=(), kwargs={})
    state.attempt_number = attempt_number
    if exc is not None:
        state.set_exception((type(exc), exc, exc.__traceback__))
    else:
        state.set_result(None)
    return state


def test_wait_prefers_retry_after_when_larger_than_backoff():
    waiter = wait_retry_after_or_backoff(wait_fixed(1), max_retry_after=60)
    state = _retry_state(RetryableBundleError(503, retry_after=30.0))
    # MUTATION: returning `base` unconditionally (dropping the max()) gives 1.0.
    assert waiter(state) == pytest.approx(30.0)


def test_wait_prefers_backoff_when_larger_than_retry_after():
    waiter = wait_retry_after_or_backoff(wait_fixed(12), max_retry_after=60)
    state = _retry_state(RetryableBundleError(503, retry_after=3.0))
    # MUTATION: returning `retry_after` unconditionally gives 3.0 and would let
    # a server shrink the operator's configured backoff.
    assert waiter(state) == pytest.approx(12.0)


def test_wait_caps_a_hostile_retry_after():
    waiter = wait_retry_after_or_backoff(wait_fixed(1), max_retry_after=60)
    state = _retry_state(RetryableBundleError(503, retry_after=3600.0))
    # MUTATION: dropping the `min(retry_after, max_retry_after)` cap stalls the
    # client for an hour on a single hostile header.
    assert waiter(state) == pytest.approx(60.0)


def test_wait_falls_back_to_backoff_without_a_retry_after():
    waiter = wait_retry_after_or_backoff(wait_fixed(7), max_retry_after=60)
    assert waiter(_retry_state(RetryableBundleError(503, retry_after=None))) == 7.0
    assert waiter(_retry_state(ValueError("boom"))) == 7.0
    assert waiter(_retry_state(None)) == 7.0


def test_wait_handles_a_state_with_no_outcome_yet():
    waiter = wait_retry_after_or_backoff(wait_fixed(3), max_retry_after=60)
    state = RetryCallState(retry_object=None, fn=None, args=(), kwargs={})
    # MUTATION: reading `retry_state.outcome.failed` without the None guard
    # raises AttributeError on the very first wait computation.
    assert waiter(state) == 3.0


def test_wait_does_not_shrink_a_backoff_larger_than_the_cap():
    """The cap bounds the *server-supplied* header, not the operator's backoff.

    POLICY_UPDATER_CONN_RETRY semantics must be unchanged.
    """
    waiter = wait_retry_after_or_backoff(wait_fixed(120), max_retry_after=60)
    state = _retry_state(RetryableBundleError(503, retry_after=5.0))
    # MUTATION: applying the cap to the whole max() would clamp this to 60.
    assert waiter(state) == pytest.approx(120.0)


# ---------------------------------------------------------------------------
# response classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_503_raises_retryable_error_carrying_retry_after(
    scripted_session, no_sleep
):
    scripted_session(
        FakeResponse(
            503, headers={"Retry-After": "30"}, body={"detail": "clone in progress"}
        )
    )
    fetcher = make_fetcher(no_sleep, attempts=1)

    with pytest.raises(RetryableBundleError) as excinfo:
        await fetcher.fetch_policy_bundle()

    # MUTATION: classifying 503 as non-retryable (or not classifying it at all)
    # breaks the type assertion and the retry_after payload.
    assert excinfo.value.status_code == 503
    assert excinfo.value.retry_after == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_429_is_retryable(scripted_session, no_sleep):
    scripted_session(FakeResponse(429, headers={"Retry-After": "5"}, body={}))
    fetcher = make_fetcher(no_sleep, attempts=1)

    with pytest.raises(RetryableBundleError) as excinfo:
        await fetcher.fetch_policy_bundle()

    # MUTATION: dropping 429 from the retryable status set makes this a plain
    # ValueError from throw_if_bad_status_code with no Retry-After.
    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_503_without_retry_after_header_is_still_retryable(
    scripted_session, no_sleep
):
    scripted_session(FakeResponse(503, headers={}, body={"detail": "nope"}))
    fetcher = make_fetcher(no_sleep, attempts=1)

    with pytest.raises(RetryableBundleError) as excinfo:
        await fetcher.fetch_policy_bundle()

    assert excinfo.value.retry_after is None


@pytest.mark.asyncio
async def test_409_is_attempted_exactly_once(scripted_session, no_sleep):
    scripted_session(FakeResponse(409, body={"detail": "branch not found"}))
    fetcher = make_fetcher(no_sleep, attempts=5)

    with pytest.raises(NonRetryableBundleError) as excinfo:
        await fetcher.fetch_policy_bundle()

    assert excinfo.value.status_code == 409
    assert "branch not found" in excinfo.value.detail
    # MUTATION: removing `retry=retry_if_not_exception_type(NonRetryableBundleError)`
    # makes this 5 requests -- the exact bug this PR fixes (a 409 hammered for ~40s).
    assert total_requests() == 1
    assert no_sleep.recorded == []


@pytest.mark.asyncio
async def test_404_is_attempted_exactly_once_and_stays_an_http_exception(
    scripted_session, no_sleep
):
    scripted_session(FakeResponse(404, body={"detail": "no such path"}))
    fetcher = make_fetcher(no_sleep, attempts=5)

    with pytest.raises(BundlePathNotFoundError) as excinfo:
        await fetcher.fetch_policy_bundle()

    # Backwards compatibility: callers that catch fastapi's HTTPException (the
    # pre-PR behaviour for 404) keep working.
    assert isinstance(excinfo.value, HTTPException)
    assert isinstance(excinfo.value, NonRetryableBundleError)
    assert excinfo.value.status_code == 404
    # MUTATION: making BundlePathNotFoundError inherit only HTTPException (i.e.
    # dropping it from the retry predicate's type) turns this into 5 requests.
    assert total_requests() == 1


@pytest.mark.asyncio
async def test_503_is_retried_and_each_wait_honours_retry_after(
    scripted_session, no_sleep
):
    scripted_session(FakeResponse(503, headers={"Retry-After": "30"}, body={}))
    fetcher = make_fetcher(no_sleep, attempts=3)

    with pytest.raises(RetryableBundleError):
        await fetcher.fetch_policy_bundle()

    assert total_requests() == 3
    # 3 attempts => 2 waits between them.
    assert len(no_sleep.recorded) == 2
    # MUTATION: leaving `wait` as the bare random-exponential (max=10) makes every
    # recorded wait <= 10 and fails here -- the "Retry-After is never read" bug.
    assert all(wait >= 30.0 for wait in no_sleep.recorded)


@pytest.mark.asyncio
async def test_retry_after_is_capped_end_to_end(
    scripted_session, no_sleep, monkeypatch
):
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 12.0)
    scripted_session(FakeResponse(503, headers={"Retry-After": "9999"}, body={}))
    fetcher = make_fetcher(no_sleep, attempts=2)

    with pytest.raises(RetryableBundleError):
        await fetcher.fetch_policy_bundle()

    # MUTATION: ignoring POLICY_UPDATER_MAX_RETRY_AFTER sleeps for 9999s.
    assert no_sleep.recorded == [pytest.approx(12.0)]


@pytest.mark.asyncio
async def test_unclassified_bad_status_is_still_retried(scripted_session, no_sleep):
    """500 has no special handling -- it keeps the pre-PR retry behaviour."""
    scripted_session(FakeResponse(500, body={"detail": "boom"}))
    fetcher = make_fetcher(no_sleep, attempts=4)

    with pytest.raises(ValueError):
        await fetcher.fetch_policy_bundle()

    # MUTATION: excluding *all* errors from retry (e.g. inverting the predicate)
    # would make this 1 request and silently weaken transient-fault handling.
    assert total_requests() == 4


@pytest.mark.asyncio
async def test_connection_errors_are_still_retried(scripted_session, no_sleep):
    scripted_session(aiohttp.ClientConnectionError("refused"))
    fetcher = make_fetcher(no_sleep, attempts=3)

    with pytest.raises(aiohttp.ClientError):
        await fetcher.fetch_policy_bundle()

    assert total_requests() == 3


@pytest.mark.asyncio
async def test_successful_fetch_returns_a_bundle(scripted_session, no_sleep):
    scripted_session(
        FakeResponse(
            200,
            body={
                "manifest": [],
                "hash": "abc123",
                "old_hash": None,
                "data_modules": [],
                "policy_modules": [],
            },
        )
    )
    fetcher = make_fetcher(no_sleep, attempts=5)

    bundle = await fetcher.fetch_policy_bundle()

    assert bundle is not None
    assert bundle.hash == "abc123"
    assert total_requests() == 1


@pytest.mark.asyncio
async def test_a_503_followed_by_a_200_succeeds(scripted_session, no_sleep):
    scripted_session(
        FakeResponse(503, headers={"Retry-After": "2"}, body={}),
        FakeResponse(
            200,
            body={
                "manifest": [],
                "hash": "def456",
                "old_hash": None,
                "data_modules": [],
                "policy_modules": [],
            },
        ),
    )
    fetcher = make_fetcher(no_sleep, attempts=5)

    bundle = await fetcher.fetch_policy_bundle()

    assert bundle.hash == "def456"
    assert total_requests() == 2
    assert no_sleep.recorded == [pytest.approx(2.0)]


@pytest.mark.asyncio
async def test_detail_extraction_survives_a_non_json_body(scripted_session, no_sleep):
    """The 409 path must not blow up when the server did not answer JSON."""
    scripted_session(FakeResponse(409, body=None))
    fetcher = make_fetcher(no_sleep, attempts=2)

    with pytest.raises(NonRetryableBundleError) as excinfo:
        await fetcher.fetch_policy_bundle()

    # MUTATION: calling `await response.json()` unguarded raises ValueError here,
    # which would be *retried* (wrong class) instead of failing fast.
    assert excinfo.value.status_code == 409


# ---------------------------------------------------------------------------
# HIGH-2: one fetch must not block the serial update queue for attempts x cap
# ---------------------------------------------------------------------------


def test_the_stop_condition_is_bounded_by_both_attempts_and_total_delay(monkeypatch):
    # operator budget (fixed 1s x 5 == 5s) is smaller than the cap, so the cap wins
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 42.0)
    monkeypatch.setattr(
        opal_client_config,
        "POLICY_UPDATER_CONN_RETRY",
        ConnRetryOptions(wait_strategy="fixed", wait_time=1, attempts=5),
    )
    fetcher = PolicyFetcher(backend_url="http://opal-server:7002", token="t")

    stop = fetcher._retry_config["stop"]
    # MUTATION: leaving `stop` as the bare stop_after_attempt lets a proxy's
    # `Retry-After: 300` hold the policy-update queue for attempts x cap.
    assert isinstance(stop, stop_any)
    assert any(isinstance(s, stop_after_attempt) for s in stop.stops)
    delay_stops = [s for s in stop.stops if isinstance(s, stop_after_delay)]
    assert len(delay_stops) == 1
    assert delay_stops[0].max_delay == pytest.approx(42.0)


@pytest.mark.asyncio
async def test_a_huge_retry_after_cannot_hold_the_fetch_past_the_cap(
    scripted_session, monkeypatch
):
    """`Retry-After: 300` from a proxy must not stall one fetch for minutes.

    Uses the real clock and real (tiny) sleeps on purpose: `stop_after_delay`
    is wall-clock based, so a faked sleep would never let it fire.
    """
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 0.2)
    monkeypatch.setattr(
        opal_client_config,
        "POLICY_UPDATER_CONN_RETRY",
        ConnRetryOptions(wait_strategy="fixed", wait_time=0.01, attempts=10),
    )
    scripted_session(FakeResponse(503, headers={"Retry-After": "300"}, body={}))
    fetcher = PolicyFetcher(backend_url="http://opal-server:7002", token="t")

    started = time.monotonic()
    with pytest.raises(RetryableBundleError):
        await fetcher.fetch_policy_bundle()
    elapsed = time.monotonic() - started

    # Without the delay bound this is 10 attempts x 0.2s == ~2s; with it, the
    # fetch gives up as soon as it has spent `cap` seconds waiting.
    assert elapsed < 0.8, f"one fetch blocked the queue for {elapsed:.2f}s"
    assert total_requests() <= 3


# ---------------------------------------------------------------------------
# LOW-1: exactly one WARNING per exhausted fetch; per-attempt logs are DEBUG
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_logs():
    records = []
    sink_id = logger.add(lambda m: records.append(m.record), level="DEBUG")
    yield records
    logger.remove(sink_id)


def _warnings(records):
    return [r for r in records if r["level"].name == "WARNING"]


def _messages(records, level):
    return [r["message"] for r in records if r["level"].name == level]


@pytest.mark.asyncio
async def test_a_retried_503_logs_one_warning_not_one_per_attempt(
    scripted_session, no_sleep, captured_logs
):
    scripted_session(FakeResponse(503, headers={"Retry-After": "30"}, body={}))
    fetcher = make_fetcher(no_sleep, attempts=4)

    with pytest.raises(RetryableBundleError):
        await fetcher.fetch_policy_bundle()

    assert total_requests() == 4
    # MUTATION: leaving the per-attempt classification at WARNING emits one line
    # per attempt, so a fleet-wide outage floods the log budget 4x over.
    warnings = _warnings(captured_logs)
    assert len(warnings) == 1, [w["message"] for w in warnings]
    assert "retryable" in warnings[0]["message"]
    assert "503" in warnings[0]["message"]
    # the per-attempt detail is still available, at debug
    assert len([m for m in _messages(captured_logs, "DEBUG") if "503" in m]) == 4


@pytest.mark.asyncio
async def test_a_409_logs_exactly_one_warning(
    scripted_session, no_sleep, captured_logs
):
    scripted_session(FakeResponse(409, body={"detail": "branch not found"}))
    fetcher = make_fetcher(no_sleep, attempts=5)

    with pytest.raises(NonRetryableBundleError):
        await fetcher.fetch_policy_bundle()

    warnings = _warnings(captured_logs)
    assert len(warnings) == 1, [w["message"] for w in warnings]
    assert "non-retryable" in warnings[0]["message"]
    assert "branch not found" in warnings[0]["message"]


@pytest.mark.asyncio
async def test_a_404_logs_exactly_one_warning(
    scripted_session, no_sleep, captured_logs
):
    scripted_session(FakeResponse(404, body={"detail": "no such path"}))
    fetcher = make_fetcher(no_sleep, attempts=5)

    with pytest.raises(BundlePathNotFoundError):
        await fetcher.fetch_policy_bundle()

    # MUTATION: leaving the "requested paths not found" line at WARNING makes
    # this 2 and breaks the one-warning-per-exhausted-fetch contract.
    warnings = _warnings(captured_logs)
    assert len(warnings) == 1, [w["message"] for w in warnings]
    assert "404" in warnings[0]["message"]


# ---------------------------------------------------------------------------
# NEW-2/NEW-5: the whole-fetch bound must never truncate the operator's own
# POLICY_UPDATER_CONN_RETRY budget
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "strategy,wait_time,max_wait,attempts,expected",
    [
        ("fixed", 0.2, 10, 5, 1.0),  # fixed -> attempts x wait_time
        ("exponential", 1, 10, 5, 50.0),  # exponential -> attempts x max_wait
        ("random_exponential", 1, 10, 5, 50.0),
        ("fixed", 2, 10, 0, 0.0),
    ],
)
def test_conn_retry_options_report_their_worst_case_total_wait(
    strategy, wait_time, max_wait, attempts, expected
):
    options = ConnRetryOptions(
        wait_strategy=strategy,
        wait_time=wait_time,
        max_wait=max_wait,
        attempts=attempts,
    )
    # MUTATION: using wait_time for the exponential strategies (or max_wait for
    # fixed) under-reports the budget, and the whole-fetch bound then truncates
    # a retry policy the operator explicitly configured.
    assert options.worstCaseTotalWait() == pytest.approx(expected)


def test_the_delay_bound_is_the_larger_of_the_cap_and_the_operator_budget(monkeypatch):
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 0.3)
    monkeypatch.setattr(
        opal_client_config,
        "POLICY_UPDATER_CONN_RETRY",
        ConnRetryOptions(wait_strategy="fixed", wait_time=0.2, attempts=5),
    )
    fetcher = PolicyFetcher(backend_url="http://opal-server:7002", token="t")

    delay_stop = [
        s
        for s in fetcher._retry_config["stop"].stops
        if isinstance(s, stop_after_delay)
    ][0]
    # MUTATION: `stop_after_delay(cap)` alone gives 0.3 here and cuts the
    # operator's 5 attempts down to 2.
    assert delay_stop.max_delay == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_the_operators_attempts_survive_a_smaller_cap(
    scripted_session, monkeypatch
):
    """`wait_fixed(0.2) x 5` with cap 0.3 must still make all 5 attempts."""
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 0.3)
    monkeypatch.setattr(
        opal_client_config,
        "POLICY_UPDATER_CONN_RETRY",
        ConnRetryOptions(wait_strategy="fixed", wait_time=0.2, attempts=5),
    )
    scripted_session(FakeResponse(503, headers={}, body={}))
    fetcher = PolicyFetcher(backend_url="http://opal-server:7002", token="t")

    with pytest.raises(RetryableBundleError):
        await fetcher.fetch_policy_bundle()

    assert total_requests() == 5


@pytest.mark.asyncio
async def test_a_zero_cap_does_not_disable_the_operators_retries(
    scripted_session, monkeypatch
):
    """NEW-5: `MAX_RETRY_AFTER=0` means "honour no server hint", not "no retries"."""
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 0.0)
    monkeypatch.setattr(
        opal_client_config,
        "POLICY_UPDATER_CONN_RETRY",
        ConnRetryOptions(wait_strategy="fixed", wait_time=0.05, attempts=3),
    )
    scripted_session(FakeResponse(503, headers={"Retry-After": "900"}, body={}))
    fetcher = PolicyFetcher(backend_url="http://opal-server:7002", token="t")

    with pytest.raises(RetryableBundleError):
        await fetcher.fetch_policy_bundle()

    # MUTATION: `stop_after_delay(0)` (no max() with the operator budget) stops
    # after a single attempt, silently disabling retries for anyone who set the
    # cap to 0 to mean "ignore Retry-After".
    assert total_requests() == 3


# ---------------------------------------------------------------------------
# NEW-4: a connection error must also cost exactly one WARNING
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_connection_error_logs_exactly_one_warning(
    scripted_session, no_sleep, captured_logs
):
    scripted_session(aiohttp.ClientConnectionError("connection refused"))
    fetcher = make_fetcher(no_sleep, attempts=4)

    with pytest.raises(aiohttp.ClientError):
        await fetcher.fetch_policy_bundle()

    assert total_requests() == 4
    # MUTATION: leaving the per-attempt "server connection error" line at WARNING
    # makes this 5 (4 per-attempt + 1 summary) -- a server outage then costs the
    # log budget one line per attempt per client.
    warnings = _warnings(captured_logs)
    assert len(warnings) == 1, [w["message"] for w in warnings]
    assert "connection refused" in warnings[0]["message"]
    assert len([m for m in _messages(captured_logs, "DEBUG") if "refused" in m]) == 4
