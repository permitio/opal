import asyncio

import pytest
from opal_server.policy.watcher.task import BasePolicyWatcherTask


class _Watcher(BasePolicyWatcherTask):
    async def trigger(self, topic, data):
        return None  # fast no-op so the created task finishes quickly


@pytest.mark.asyncio
async def test_done_tasks_are_all_removed():
    w = _Watcher(pubsub_endpoint=None)

    async def _done():
        return None

    # three already-finished tasks pre-loaded into the list
    finished = [asyncio.create_task(_done()) for _ in range(3)]
    await asyncio.gather(*finished)
    w._webhook_tasks = list(finished)

    await w._on_webhook("webhook", None)

    # all 3 done ones removed...
    remaining_done = [t for t in w._webhook_tasks if t in finished]
    assert remaining_done == [], f"stale done tasks leaked: {remaining_done}"
    # ...and exactly the one freshly scheduled trigger task survives.
    survivors = [t for t in w._webhook_tasks if t not in finished]
    assert len(w._webhook_tasks) == 1
    assert len(survivors) == 1, f"new trigger task not scheduled: {w._webhook_tasks}"

    # Await the trigger task directly (not sleep(0)) so the test doesn't depend
    # on scheduler tick ordering.
    await asyncio.gather(*survivors)


class _FailingWatcher(BasePolicyWatcherTask):
    async def trigger(self, topic, data):
        raise RuntimeError("trigger blew up")


@pytest.mark.asyncio
async def test_failed_trigger_exception_is_retrieved_and_logged():
    """Sweeping a failed trigger task must retrieve and log its exception, not
    silently drop the reference (asyncio's 'exception was never retrieved')."""
    from opal_common.logger import logger as opal_logger

    w = _FailingWatcher(pubsub_endpoint=None)

    await w._on_webhook("webhook", None)  # schedules a trigger that raises
    failed = list(w._webhook_tasks)
    await asyncio.gather(*failed, return_exceptions=True)

    records = []
    sink_id = opal_logger.add(lambda m: records.append(str(m)), level="ERROR")
    try:
        await w._on_webhook("webhook", None)  # sweep must log the failure
    finally:
        opal_logger.remove(sink_id)

    assert failed[0] not in w._webhook_tasks, "failed task not swept"
    assert any(
        "Webhook trigger task failed" in r and "trigger blew up" in r for r in records
    ), f"failure not logged: {records}"

    await asyncio.gather(*w._webhook_tasks, return_exceptions=True)


class _CredentialLeakingWatcher(BasePolicyWatcherTask):
    async def trigger(self, topic, data):
        raise RuntimeError("fetch https://user:secret@host/repo failed")


@pytest.mark.asyncio
async def test_failed_trigger_log_redacts_credentialed_url():
    """A git exception can embed a credentialed remote URL verbatim; the
    sweep's failure log must not leak it."""
    from opal_common.logger import logger as opal_logger

    w = _CredentialLeakingWatcher(pubsub_endpoint=None)

    await w._on_webhook("webhook", None)  # schedules a trigger that raises
    failed = list(w._webhook_tasks)
    await asyncio.gather(*failed, return_exceptions=True)

    records = []
    sink_id = opal_logger.add(lambda m: records.append(str(m)), level="ERROR")
    try:
        await w._on_webhook("webhook", None)  # sweep must log the failure
    finally:
        opal_logger.remove(sink_id)

    assert any("Webhook trigger task failed" in r for r in records), records
    assert any("://***@" in r for r in records), records
    assert not any("secret" in r for r in records), records

    await asyncio.gather(*w._webhook_tasks, return_exceptions=True)


class _HangingWatcher(BasePolicyWatcherTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = asyncio.Event()

    async def trigger(self, topic, data):
        self.started.set()
        await asyncio.Event().wait()  # hangs until cancelled


@pytest.mark.asyncio
async def test_stop_cancels_and_gathers_inflight_trigger():
    w = _HangingWatcher(pubsub_endpoint=None)
    await w._on_webhook("webhook", None)
    await asyncio.wait_for(w.started.wait(), timeout=5)

    await w.stop()  # must cancel the hung trigger AND await it (gather)

    assert all(t.cancelled() for t in w._webhook_tasks)
