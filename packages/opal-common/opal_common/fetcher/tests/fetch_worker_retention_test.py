"""Regression test for fetch-worker frame retention (issues #770 / #844).

A fetch worker loops `while True: event, callback = await queue.get(); ...`. Python
keeps a frame's locals bound until they are reassigned or the frame exits, so an
idle worker blocked on the next `queue.get()` used to keep the PREVIOUS fetch's
locals (`event`, `fetcher`, `res`, `data`) alive — pinning the last fetched
dataset (and its HTTP response) in memory, one retained copy per worker, until
process restart. This test fails if that cleanup is removed.
"""

import asyncio
import gc
import weakref

import pytest
from opal_common.fetcher import FetchingEngine
from opal_common.fetcher.fetch_provider import BaseFetchProvider


class _Payload:
    """A weakref-able stand-in for a large fetched dataset."""


class _SentinelProvider(BaseFetchProvider):
    async def _fetch_(self):
        return _Payload()

    async def _process_(self, data):
        return data


@pytest.mark.asyncio
async def test_idle_worker_does_not_retain_last_payload():
    async with FetchingEngine(worker_count=1) as engine:
        engine.register.register_fetcher("SentinelProvider", _SentinelProvider)

        result = await engine.handle_url("sentinel://x", fetcher="SentinelProvider")
        assert isinstance(result, _Payload)

        ref = weakref.ref(result)
        del result  # drop the caller's reference

        # The single worker is now idle, blocked on the next queue.get(). Its frame
        # must not still bind the payload from the fetch it just completed.
        collected = False
        for _ in range(20):
            await asyncio.sleep(0.02)
            gc.collect()
            if ref() is None:
                collected = True
                break

        assert collected, (
            "fetch worker retained the last fetched payload in its frame while idle "
            "-> per-worker memory high-water mark (regression of #770/#844 fix)"
        )
