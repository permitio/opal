"""Tests for `PolicyUpdater`'s deferred bundle re-fetch.

Before this change, once `fetch_policy_bundle` exhausted its tenacity attempts
(~40s with the shipped defaults) `update_policy` recorded the error and *nothing
re-scheduled the fetch*. A PDP that asked for its bundle while the server was
still cloning the scope's repo (`503 + Retry-After: 30`) would sit on a stale or
empty policy store until the next pub/sub message or WebSocket reconnect -- which,
for a low-churn scope, can be hours.

These tests pin the deferred re-fetch: exactly one pending timer, cancelled by
success / a new update / `stop()`, bounded in rounds, and never armed for an
error the server told us will not fix itself.
"""

import asyncio
import os
import sys

import pytest

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from opal_client.config import opal_client_config
from opal_client.policy import updater as updater_module
from opal_client.policy.fetcher import (
    BundlePathNotFoundError,
    NonRetryableBundleError,
    RetryableBundleError,
)
from opal_client.policy.updater import PolicyUpdater
from opal_common.schemas.policy import PolicyBundle

# ---------------------------------------------------------------------------
# test doubles
# ---------------------------------------------------------------------------


def make_bundle(commit_hash: str = "abc123") -> PolicyBundle:
    return PolicyBundle(
        manifest=[], hash=commit_hash, data_modules=[], policy_modules=[]
    )


class FakeTransaction:
    def __init__(self, store):
        self._store = store

    def _update_remote_status(self, url, status, error):
        self._store.remote_statuses.append((url, status, error))

    async def set_policies(self, bundle):
        self._store.set_policies_calls.append(bundle)


class FakeTransactionContext:
    def __init__(self, store):
        self._store = store

    async def __aenter__(self):
        return FakeTransaction(self._store)

    async def __aexit__(self, *args):
        return False


class FakePolicyStore:
    def __init__(self):
        self.version = None
        self.remote_statuses = []
        self.set_policies_calls = []

    async def get_policy_version(self):
        return self.version

    def transaction_context(self, bundle_hash, transaction_type=None):
        return FakeTransactionContext(self)


class FakeLifecycleComponent:
    """Stands in for DataFetcher / CallbacksReporter (start+stop only)."""

    def __init__(self):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class FakePolicyFetcher:
    """Replaces PolicyFetcher; replays a scripted list of outcomes."""

    policy_endpoint_url = "http://opal-server:7002/scopes/s1/policy"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def fetch_policy_bundle(self, directories=["."], base_hash=None):
        self.calls.append((tuple(directories), base_hash))
        outcome = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_updater(*outcomes) -> PolicyUpdater:
    updater = PolicyUpdater(
        token="t",
        pubsub_url="ws://opal-server:7002/ws",
        subscription_directories=["."],
        policy_store=FakePolicyStore(),
        data_fetcher=FakeLifecycleComponent(),
    )
    updater._policy_fetcher = FakePolicyFetcher(*outcomes)
    updater._callbacks_reporter = FakeLifecycleComponent()
    return updater


async def drain():
    """Let scheduled tasks reach their first suspension point."""
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.fixture
def no_jitter(monkeypatch):
    """Makes the deferred delay deterministic (jitter is tested separately)."""
    monkeypatch.setattr(updater_module, "_jittered", lambda delay: delay)


# ---------------------------------------------------------------------------
# delay computation
# ---------------------------------------------------------------------------


def test_deferred_delay_honours_retry_after(no_jitter):
    updater = make_updater()
    # MUTATION: ignoring `retry_after` and always returning the base backoff
    # gives 5.0 and fails -- the server's "come back in 30s" would be discarded.
    assert updater._deferred_refetch_delay(30.0, round_index=1) == pytest.approx(30.0)


def test_deferred_delay_falls_back_to_the_base_when_no_retry_after(no_jitter):
    updater = make_updater()
    # MUTATION: returning 0 when retry_after is None turns the deferral into a
    # busy-loop against a server that is already refusing us.
    assert updater._deferred_refetch_delay(None, round_index=1) == pytest.approx(
        updater_module.DEFERRED_REFETCH_BASE_SECONDS
    )


def test_deferred_delay_backs_off_across_rounds(no_jitter):
    updater = make_updater()
    first = updater._deferred_refetch_delay(None, round_index=1)
    second = updater._deferred_refetch_delay(None, round_index=2)
    third = updater._deferred_refetch_delay(None, round_index=3)
    # MUTATION: dropping the `2 ** (round_index - 1)` factor makes all three equal.
    assert second > first
    assert third > second


def test_deferred_delay_is_capped(monkeypatch, no_jitter):
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 60.0)
    updater = make_updater()
    # MUTATION: dropping the cap lets round 20 compute 5 * 2**19 == ~2.9 days.
    assert updater._deferred_refetch_delay(None, round_index=20) == pytest.approx(60.0)
    assert updater._deferred_refetch_delay(99999.0, round_index=1) == pytest.approx(
        60.0
    )


# ---------------------------------------------------------------------------
# scheduling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exhausted_retryable_schedules_exactly_one_deferred_refetch():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)

    # MUTATION: not scheduling at all (the pre-PR behaviour) leaves this None --
    # the client would then sit stale until the next pub/sub message.
    assert updater._deferred_refetch_task is not None
    assert not updater._deferred_refetch_task.done()
    assert updater._deferred_refetch_rounds == 1

    await updater.stop()


@pytest.mark.asyncio
async def test_a_second_failure_while_one_is_pending_does_not_stack_timers():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)
    first_task = updater._deferred_refetch_task
    await updater.update_policy(["."], force_full_update=False)

    # MUTATION: dropping the "already pending" guard creates a second task, and
    # every failed round would multiply the number of in-flight timers.
    assert updater._deferred_refetch_task is first_task
    assert updater._deferred_refetch_rounds == 1
    assert not first_task.cancelled()

    await updater.stop()


@pytest.mark.asyncio
async def test_a_successful_fetch_cancels_the_pending_deferred_refetch():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)
    pending = updater._deferred_refetch_task
    assert pending is not None

    updater._policy_fetcher.outcomes = [make_bundle()]
    await updater.update_policy(["."], force_full_update=False)
    await drain()

    # MUTATION: not cancelling on success leaves a stale timer that re-fetches
    # the bundle for no reason (and keeps the round counter climbing).
    assert updater._deferred_refetch_task is None
    assert pending.cancelled()
    assert updater._deferred_refetch_rounds == 0

    await updater.stop()


@pytest.mark.asyncio
async def test_a_new_incoming_policy_update_replaces_the_pending_deferred_refetch():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)
    pending = updater._deferred_refetch_task
    assert pending is not None

    await updater.trigger_update_policy(["."], force_full_update=True)
    await drain()

    # MUTATION: leaving the timer armed means the fresh update we just queued
    # gets followed by a redundant deferred re-fetch of the same bundle.
    assert updater._deferred_refetch_task is None
    assert pending.cancelled()
    assert updater._policy_update_queue.qsize() == 1

    await updater.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        NonRetryableBundleError(409, detail="branch could not be resolved"),
        BundlePathNotFoundError(detail="requested path not found"),
    ],
)
async def test_non_retryable_errors_are_never_rescheduled(error):
    updater = make_updater(error)

    await updater.update_policy(["."], force_full_update=False)

    # MUTATION: scheduling on *any* fetch error (rather than only on
    # RetryableBundleError) re-fetches a 409 forever, which is exactly the
    # "hammer a permanent failure" behaviour the server contract rules out.
    assert updater._deferred_refetch_task is None
    assert updater._deferred_refetch_rounds == 0

    await updater.stop()


@pytest.mark.asyncio
async def test_unclassified_errors_are_not_rescheduled():
    """Connection errors / 5xx keep their pre-PR behaviour (no deferral)."""
    updater = make_updater(ValueError("unexpected response code 500"))

    await updater.update_policy(["."], force_full_update=False)

    assert updater._deferred_refetch_task is None

    await updater.stop()


@pytest.mark.asyncio
async def test_stop_cancels_the_pending_deferred_refetch():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)
    pending = updater._deferred_refetch_task
    assert pending is not None

    await updater.stop()
    await drain()

    # MUTATION: forgetting to cancel in stop() leaks the timer past shutdown and
    # produces "Task was destroyed but it is pending!" on client teardown.
    assert pending.cancelled()
    assert updater._deferred_refetch_task is None


@pytest.mark.asyncio
async def test_deferred_rounds_are_bounded(monkeypatch):
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_DEFERRED_ROUNDS", 3)
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    for _ in range(3):
        # each round: fail, arm a timer, then pretend the timer fired
        await updater.update_policy(["."], force_full_update=False)
        assert updater._deferred_refetch_task is not None
        updater._deferred_refetch_task.cancel()
        updater._deferred_refetch_task = None

    assert updater._deferred_refetch_rounds == 3

    await updater.update_policy(["."], force_full_update=False)

    # MUTATION: dropping the `rounds >= max` guard lets a permanently-503 scope
    # re-fetch forever, which is a slow-motion self-inflicted DoS on the server.
    assert updater._deferred_refetch_task is None
    assert updater._deferred_refetch_rounds == 3

    await updater.stop()


@pytest.mark.asyncio
async def test_rescheduling_can_be_disabled_by_config(monkeypatch):
    monkeypatch.setattr(
        opal_client_config, "POLICY_UPDATER_RESCHEDULE_ON_RETRYABLE", False
    )
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)

    # MUTATION: ignoring POLICY_UPDATER_RESCHEDULE_ON_RETRYABLE removes the
    # operator's escape hatch back to the pre-PR behaviour.
    assert updater._deferred_refetch_task is None
    assert updater._deferred_refetch_rounds == 0

    await updater.stop()


@pytest.mark.asyncio
async def test_the_deferred_timer_enqueues_the_original_update_arguments(monkeypatch):
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))
    monkeypatch.setattr(
        updater, "_deferred_refetch_delay", lambda retry_after, round_index: 0.01
    )

    await updater.update_policy(["sub/dir"], force_full_update=True)
    assert updater._policy_update_queue.qsize() == 0

    await asyncio.sleep(0.05)

    # MUTATION: enqueueing `(None, False)` instead of the captured arguments
    # would silently widen the subscription and drop force_full_update.
    assert updater._policy_update_queue.qsize() == 1
    assert updater._policy_update_queue.get_nowait() == (["sub/dir"], True)
    # the timer clears its own handle once it has fired
    assert updater._deferred_refetch_task is None

    await updater.stop()


@pytest.mark.asyncio
async def test_the_failed_fetch_is_still_recorded_on_the_store_transaction():
    """Scheduling a retry must not swallow the error report to the policy
    store."""
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)

    assert len(updater._policy_store.remote_statuses) == 1
    url, ok, error = updater._policy_store.remote_statuses[0]
    assert ok is False
    assert "503" in error

    await updater.stop()


# ---------------------------------------------------------------------------
# HIGH-1: jitter, so a fleet does not re-fetch in lockstep
# ---------------------------------------------------------------------------


def test_jittered_stays_inside_the_lower_half_of_its_window():
    for _ in range(500):
        assert 5.0 <= updater_module._jittered(10.0) <= 10.0


def test_jittered_actually_spreads_the_delay():
    samples = {updater_module._jittered(20.0) for _ in range(200)}
    # MUTATION: `return delay` (no jitter) collapses this to a single value, and
    # every client in the fleet re-fetches on the same tick.
    assert len(samples) > 100


def test_the_deferred_delay_routes_through_the_jitter(monkeypatch):
    seen = []

    def fake_jitter(delay):
        seen.append(delay)
        return 1.23

    monkeypatch.setattr(updater_module, "_jittered", fake_jitter)
    updater = make_updater()

    assert updater._deferred_refetch_delay(30.0, round_index=1) == pytest.approx(1.23)
    # MUTATION: computing the delay without calling _jittered leaves `seen` empty.
    assert seen == [pytest.approx(30.0)]


def test_two_clients_in_the_same_round_get_different_delays():
    a = make_updater()
    b = make_updater()
    draws_a = [a._deferred_refetch_delay(30.0, round_index=2) for _ in range(50)]
    draws_b = [b._deferred_refetch_delay(30.0, round_index=2) for _ in range(50)]
    assert draws_a != draws_b


# ---------------------------------------------------------------------------
# MEDIUM-1: a zero ceiling must not collapse the deferred backoff
# ---------------------------------------------------------------------------


def test_a_zero_ceiling_does_not_collapse_the_deferred_delay(monkeypatch, no_jitter):
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 0.0)
    updater = make_updater()

    # MUTATION: without the base-seconds floor both of these are 0.0, and the
    # client burns all 20 deferred rounds back-to-back with no wait at all.
    assert updater._deferred_refetch_delay(None, round_index=1) == pytest.approx(5.0)
    assert updater._deferred_refetch_delay(30.0, round_index=3) == pytest.approx(5.0)


def test_a_tiny_ceiling_is_still_floored(monkeypatch, no_jitter):
    monkeypatch.setattr(opal_client_config, "POLICY_UPDATER_MAX_RETRY_AFTER", 0.5)
    updater = make_updater()
    assert updater._deferred_refetch_delay(0.1, round_index=1) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# MEDIUM-2: only a genuine policy update resets the round counter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_websocket_reconnect_does_not_reset_the_round_counter():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)
    assert updater._deferred_refetch_rounds == 1
    updater._deferred_refetch_task.cancel()
    updater._deferred_refetch_task = None

    # _on_connect fires on every reconnect, and reconnects are frequent
    await updater._on_connect(client=None, channel=None)

    # MUTATION: resetting the counter in trigger_update_policy (as the first
    # version did) means a client that reconnects every few minutes never
    # reaches MAX_DEFERRED_ROUNDS and re-fetches forever.
    assert updater._deferred_refetch_rounds == 1

    await updater.stop()


@pytest.mark.asyncio
async def test_a_genuine_incoming_policy_update_resets_the_round_counter():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))

    await updater.update_policy(["."], force_full_update=False)
    assert updater._deferred_refetch_rounds == 1

    await updater._update_policy_callback(
        data={
            "old_policy_hash": "aaa",
            "new_policy_hash": "bbb",
            "changed_directories": ["."],
        },
        topic="policy:.",
    )

    # MUTATION: never resetting means a scope that recovers after 20 rounds
    # stays permanently un-deferrable.
    assert updater._deferred_refetch_rounds == 0

    await updater.stop()


@pytest.mark.asyncio
async def test_a_malformed_policy_update_message_does_not_reset_the_counter():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))
    await updater.update_policy(["."], force_full_update=False)

    await updater._update_policy_callback(data=None, topic="policy:.")
    await updater._update_policy_callback(data={"garbage": True}, topic="policy:.")

    assert updater._deferred_refetch_rounds == 1

    await updater.stop()


# ---------------------------------------------------------------------------
# MEDIUM-3: a policy-store read failure must not swallow the deferral
# ---------------------------------------------------------------------------


class ExplodingVersionStore(FakePolicyStore):
    async def get_policy_version(self):
        raise RuntimeError("OPA is restarting")


@pytest.mark.asyncio
async def test_a_policy_store_read_failure_still_fetches_and_still_defers():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))
    updater._policy_store = ExplodingVersionStore()

    await updater.update_policy(["."], force_full_update=False)

    # falls back to a full bundle rather than aborting
    assert updater._policy_fetcher.calls == [((".",), None)]
    # MUTATION: leaving get_policy_version outside the try lets the RuntimeError
    # escape update_policy, so the deferral never arms and a client whose OPA
    # restarted alongside the server never recovers on its own.
    assert updater._deferred_refetch_task is not None

    await updater.stop()


# ---------------------------------------------------------------------------
# MEDIUM-4: the deferral round-trips through the real update loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_deferral_round_trips_through_handle_policy_updates(monkeypatch):
    """Fail(503) -> timer -> queue -> handler -> update_policy -> success."""
    updater = make_updater(
        RetryableBundleError(503, retry_after=30.0), make_bundle("recovered")
    )
    monkeypatch.setattr(
        updater, "_deferred_refetch_delay", lambda retry_after, round_index: 0.0
    )
    updater._policy_update_task = asyncio.create_task(updater.handle_policy_updates())

    await updater.trigger_update_policy(["."], force_full_update=False)

    loop = asyncio.get_event_loop()
    deadline = loop.time() + 3.0
    while not updater._policy_store.set_policies_calls:
        if loop.time() > deadline:
            pytest.fail("the deferred re-fetch never round-tripped through the loop")
        await asyncio.sleep(0.01)

    # MUTATION: if the timer never re-queues (or the handler never picks it up)
    # this test times out -- it is the only end-to-end proof the loop closes.
    assert len(updater._policy_fetcher.calls) == 2
    assert updater._policy_store.set_policies_calls[0].hash == "recovered"
    assert updater._deferred_refetch_rounds == 0
    assert updater._deferred_refetch_task is None

    await updater.stop()


# ---------------------------------------------------------------------------
# LOW-2: stop() must await the timer it cancelled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_awaits_the_timer_it_cancelled():
    updater = make_updater(RetryableBundleError(503, retry_after=30.0))
    await updater.update_policy(["."], force_full_update=False)
    pending = updater._deferred_refetch_task
    assert pending is not None

    await updater.stop()

    # MUTATION: cancelling without awaiting leaves the task un-finalised at the
    # moment stop() returns, which surfaces as "Task was destroyed but it is
    # pending!" when the client shuts down.
    assert pending.done()
