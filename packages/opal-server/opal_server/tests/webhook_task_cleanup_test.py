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
    await asyncio.sleep(0)  # let the newly created trigger task finish

    # all 3 done ones removed...
    remaining_done = [t for t in w._webhook_tasks if t in finished]
    assert remaining_done == [], f"stale done tasks leaked: {remaining_done}"
    # ...and exactly the one freshly scheduled trigger task survives.
    survivors = [t for t in w._webhook_tasks if t not in finished]
    assert len(w._webhook_tasks) == 1
    assert len(survivors) == 1, f"new trigger task not scheduled: {w._webhook_tasks}"

    await asyncio.gather(*survivors)  # drain the dangling task
