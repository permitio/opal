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


# ---------------------------------------------------------------------------
# delay computation
# ---------------------------------------------------------------------------


def test_deferred_delay_honours_retry_after():
    updater = make_updater()
    # MUTATION: ignoring `retry_after` and always returning the base backoff
    # gives 5.0 and fails -- the server's "come back in 30s" would be discarded.
    assert updater._deferred_refetch_delay(30.0, round_index=1) == pytest.approx(30.0)


def test_deferred_delay_falls_back_to_the_base_when_no_retry_after():
    updater = make_updater()
    # MUTATION: returning 0 when retry_after is None turns the deferral into a
    # busy-loop against a server that is already refusing us.
    assert updater._deferred_refetch_delay(None, round_index=1) == pytest.approx(
        updater_module.DEFERRED_REFETCH_BASE_SECONDS
    )


def test_deferred_delay_backs_off_across_rounds():
    updater = make_updater()
    first = updater._deferred_refetch_delay(None, round_index=1)
    second = updater._deferred_refetch_delay(None, round_index=2)
    third = updater._deferred_refetch_delay(None, round_index=3)
    # MUTATION: dropping the `2 ** (round_index - 1)` factor makes all three equal.
    assert second > first
    assert third > second


def test_deferred_delay_is_capped(monkeypatch):
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
