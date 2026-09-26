"""Regression test for data-update backpressure (issues #844 / #770).

Data updates are triggered fire-and-forget into an unbounded task pool, and each
update fetches+writes its dataset. Without a bound, a burst of updates (a reconnect
storm, or frequent periodic updates against a slow policy store) stacks an unbounded
number of in-flight datasets in memory, which the allocator retains as a high-water
mark. DataUpdater caps concurrent fetch+write via an asyncio.Semaphore
(DATA_UPDATER_MAX_CONCURRENT_UPDATES / max_concurrent_data_updates).

This test asserts the cap is honored (peak concurrent writes <= cap) AND that no
update is dropped (every triggered update is applied). It FAILS if the semaphore
is removed: peak concurrent writes then equals the burst size.
"""

import asyncio
from typing import List, Optional

import pytest
from opal_client.data.updater import DataUpdater
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_common.schemas.data import DataSourceEntry, DataUpdate

DATA_TOPICS = ["policy_data"]


class _SlowConcurrencyTrackingStore(BasePolicyStoreClient):
    """A slow policy store that records the peak number of concurrent
    writes."""

    def __init__(self, write_delay: float = 0.2):
        super().__init__()
        self._write_delay = write_delay
        self.writes = 0
        self.active = 0
        self.peak_active = 0

    async def _slow_write(self):
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        try:
            await asyncio.sleep(self._write_delay)
            self.writes += 1
        finally:
            self.active -= 1

    async def set_policy_data(self, policy_data, path: str = "", transaction_id=None):
        await self._slow_write()

    async def patch_policy_data(self, policy_data, path: str = "", transaction_id=None):
        await self._slow_write()

    # --- unused abstract surface ---
    async def set_policy(self, *a, **k):
        ...

    async def get_policy(self, *a, **k):
        ...

    async def delete_policy(self, *a, **k):
        ...

    async def get_policy_module_ids(self, *a, **k):
        ...

    async def set_policies(self, *a, **k):
        ...

    async def get_policy_version(self, *a, **k):
        return None

    async def get_data(self, *a, **k):
        return {}

    async def delete_policy_data(self, *a, **k):
        ...

    async def get_data_with_input(self, *a, **k):
        ...

    async def init_healthcheck_policy(self, *a, **k):
        ...

    async def log_transaction(self, *a, **k):
        ...

    async def is_ready(self, *a, **k):
        return True

    async def is_healthy(self, *a, **k):
        return True

    async def full_export(self, *a, **k):
        ...

    async def full_import(self, *a, **k):
        ...


class _InstantFetcher:
    """Stand-in DataFetcher that returns a small dataset without real I/O."""

    async def handle_url(self, url: str, config=None, data=None):
        return {"value": url}


def _make_updater(store, cap: int) -> DataUpdater:
    return DataUpdater(
        pubsub_url="ws://localhost:7000/ws",
        policy_store=store,
        data_fetcher=_InstantFetcher(),
        data_topics=DATA_TOPICS,
        should_send_reports=False,
        max_concurrent_data_updates=cap,
    )


@pytest.mark.asyncio
async def test_concurrent_data_updates_are_bounded_by_cap():
    """A burst of N updates must never exceed `cap` concurrent writes, and all
    N must still be applied (no silent dropping)."""
    cap = 3
    burst = 30
    store = _SlowConcurrencyTrackingStore(write_delay=0.2)
    updater = _make_updater(store, cap=cap)

    for i in range(burst):
        update = DataUpdate(
            reason="burst",
            entries=[
                DataSourceEntry(
                    url=f"http://example/{i}",
                    topics=DATA_TOPICS,
                    dst_path=f"/p{i}",  # distinct paths -> no lock serialization
                    save_method="PUT",
                )
            ],
        )
        update.id = f"u{i}"
        await updater.trigger_data_update(update)

    # Wait for the whole backlog to drain.
    await asyncio.wait_for(updater._tasks.shutdown(), timeout=30)

    # No-drop: every triggered update was applied.
    assert store.writes == burst
    # Bounded: concurrency never exceeded the cap (would be ~burst without the gate).
    assert store.peak_active <= cap
    # Sanity: the burst really was larger than the cap, so this is a meaningful bound.
    assert burst > cap


@pytest.mark.asyncio
async def test_cap_actually_throttles_relative_to_burst():
    """With a tiny cap the observed peak concurrency tracks the cap, not the
    burst size — the property that fails if the semaphore is removed."""
    cap = 2
    burst = 20
    store = _SlowConcurrencyTrackingStore(write_delay=0.15)
    updater = _make_updater(store, cap=cap)

    for i in range(burst):
        update = DataUpdate(
            reason="burst",
            entries=[
                DataSourceEntry(
                    url=f"http://example/{i}",
                    topics=DATA_TOPICS,
                    dst_path=f"/p{i}",
                    save_method="PUT",
                )
            ],
        )
        update.id = f"u{i}"
        await updater.trigger_data_update(update)

    await asyncio.wait_for(updater._tasks.shutdown(), timeout=30)

    assert store.writes == burst
    assert store.peak_active <= cap
