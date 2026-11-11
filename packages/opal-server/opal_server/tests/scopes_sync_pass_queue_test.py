"""The leader runs one scope sync pass at a time: at most one runs and one is
queued, and a request made while a pass is queued joins it.

Every request is served by a pass that started after it was made. The queued
pass merges its requests' flags: it polls only when every request asked for
poll-only, and honours the source backoff only when every request does, so a
refresh-all that joins a periodic request still gets a full pass without
backoff.
"""
import asyncio
import contextlib

import pytest
from opal_common.logger import logger
from opal_server.scopes.task import _SyncPassQueue

_END_LINE = "Scope sync pass for"


class _Passes:
    """A run_pass that records each call's flags and blocks until released."""

    def __init__(self):
        self.calls = []
        self.started_at = []
        self._release = []
        self._clock = 0
        self.raise_in = {}

    def tick(self):
        self._clock += 1
        return self._clock

    async def __call__(self, only_poll_updates, honor_backoff):
        index = len(self.calls)
        self.calls.append((only_poll_updates, honor_backoff))
        self.started_at.append(self.tick())
        release = asyncio.Event()
        self._release.append(release)
        await release.wait()
        if index in self.raise_in:
            raise self.raise_in[index]

    async def started(self, count):
        for _ in range(10_000):
            if len(self.calls) >= count:
                return
            await asyncio.sleep(0)
        raise AssertionError(f"{count} passes never started: {self.calls}")

    def release(self, index):
        self._release[index].set()


async def _settle():
    for _ in range(50):
        await asyncio.sleep(0)


@pytest.fixture
def records():
    captured = []
    sink = logger.add(lambda m: captured.append(m.record), level="DEBUG")
    yield captured
    logger.remove(sink)


@contextlib.asynccontextmanager
async def _queue():
    passes = _Passes()
    q = _SyncPassQueue(passes)
    try:
        yield q, passes
    finally:
        await q.stop()


def _full():
    return {"only_poll_updates": False, "honor_backoff": False}


@pytest.mark.asyncio
async def test_requests_during_a_pass_share_one_follow_up_pass():
    async with _queue() as (q, passes):
        a = asyncio.create_task(q.request(**_full()))
        await passes.started(1)
        b, c, d = (asyncio.create_task(q.request(**_full())) for _ in range(3))
        await _settle()
        assert len(passes.calls) == 1

        passes.release(0)
        await passes.started(2)
        await _settle()
        assert a.done()
        assert not any(t.done() for t in (b, c, d)), "served by the pass that ran"

        passes.release(1)
        await asyncio.wait_for(asyncio.gather(a, b, c, d), timeout=5)
        await _settle()
        assert len(passes.calls) == 2


@pytest.mark.asyncio
async def test_two_requests_at_once_run_one_pass():
    async with _queue() as (q, passes):
        both = asyncio.gather(q.request(**_full()), q.request(**_full()))
        await passes.started(1)
        passes.release(0)
        await asyncio.wait_for(both, timeout=5)
        await _settle()
        assert len(passes.calls) == 1


@pytest.mark.asyncio
async def test_each_request_is_served_by_a_pass_started_after_it():
    async with _queue() as (q, passes):
        made = {}

        async def _request(name):
            made[name] = passes.tick()
            await q.request(**_full())

        first = asyncio.create_task(_request("first"))
        await passes.started(1)
        second = asyncio.create_task(_request("second"))
        await _settle()
        assert passes.started_at[0] > made["first"]
        assert made["second"] > passes.started_at[0], "made after pass 0 started"

        passes.release(0)
        await passes.started(2)
        await _settle()
        assert first.done()
        assert not second.done(), "served by a pass that started before it"
        assert passes.started_at[1] > made["second"]

        passes.release(1)
        await asyncio.wait_for(asyncio.gather(first, second), timeout=5)


@pytest.mark.asyncio
async def test_flags_merge_full_and_no_backoff_win():
    async with _queue() as (q, passes):
        running = asyncio.create_task(
            q.request(only_poll_updates=True, honor_backoff=True)
        )
        await passes.started(1)
        periodic = asyncio.create_task(
            q.request(only_poll_updates=True, honor_backoff=True)
        )
        refresh_all = asyncio.create_task(
            q.request(only_poll_updates=False, honor_backoff=False)
        )
        await _settle()
        passes.release(0)
        await passes.started(2)
        assert passes.calls[1] == (False, False)

        lone_periodic = asyncio.create_task(
            q.request(only_poll_updates=True, honor_backoff=True)
        )
        await _settle()
        passes.release(1)
        await passes.started(3)
        assert passes.calls[2] == (True, True)

        poll_but_no_backoff = [
            asyncio.create_task(q.request(only_poll_updates=True, honor_backoff=True)),
            asyncio.create_task(q.request(only_poll_updates=True, honor_backoff=False)),
        ]
        await _settle()
        passes.release(2)
        await passes.started(4)
        assert passes.calls[3] == (True, False)
        passes.release(3)
        await asyncio.wait_for(
            asyncio.gather(
                running, periodic, refresh_all, lone_periodic, *poll_but_no_backoff
            ),
            timeout=5,
        )


@pytest.mark.asyncio
async def test_a_raising_pass_resolves_waiters_and_runs_the_queued_one(records):
    async with _queue() as (q, passes):
        passes.raise_in[0] = OSError("disk")
        a = asyncio.create_task(q.request(**_full()))
        await passes.started(1)
        b = asyncio.create_task(q.request(**_full()))
        await _settle()

        passes.release(0)
        await asyncio.wait_for(a, timeout=5)  # returns, does not raise
        await passes.started(2)
        passes.release(1)
        await asyncio.wait_for(b, timeout=5)

        errors = [r for r in records if r["level"].name == "ERROR"]
        assert len(errors) == 1, [r["message"] for r in errors]
        assert errors[0]["exception"] is not None, "logged without its traceback"
        assert "disk" in str(errors[0]["exception"].value)


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_the_shared_pass():
    async with _queue() as (q, passes):
        running = asyncio.create_task(q.request(**_full()))
        await passes.started(1)
        leaver = asyncio.create_task(q.request(**_full()))
        stayer = asyncio.create_task(q.request(**_full()))
        await _settle()

        leaver.cancel()
        await _settle()
        passes.release(0)
        await passes.started(2)
        passes.release(1)
        await asyncio.wait_for(asyncio.gather(running, stayer), timeout=5)
        assert leaver.cancelled()
        assert len(passes.calls) == 2


@pytest.mark.asyncio
async def test_a_cancelled_waiter_of_the_running_pass_leaves_it_running():
    async with _queue() as (q, passes):
        leaver = asyncio.create_task(q.request(**_full()))
        stayer = asyncio.create_task(q.request(**_full()))
        await passes.started(1)
        leaver.cancel()
        await _settle()
        passes.release(0)
        await asyncio.wait_for(stayer, timeout=5)
        assert leaver.cancelled()
        assert len(passes.calls) == 1


@pytest.mark.asyncio
async def test_stop_cancels_the_running_pass_and_releases_waiters():
    cancelled = asyncio.Event()

    async def _run_pass(only_poll_updates, honor_backoff):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    q = _SyncPassQueue(_run_pass)
    running = asyncio.create_task(q.request(**_full()))
    for _ in range(50):
        await asyncio.sleep(0)
    queued = asyncio.create_task(q.request(**_full()))
    await _settle()

    await asyncio.wait_for(q.stop(), timeout=5)
    assert cancelled.is_set(), "the running pass was not cancelled"
    done, pending = await asyncio.wait({running, queued}, timeout=5)
    assert not pending, "a waiter was left waiting after stop()"
    assert all(t.cancelled() for t in done)

    await asyncio.wait_for(q.stop(), timeout=5)  # a second stop is a no-op


@pytest.mark.asyncio
async def test_request_after_stop_runs_no_pass():
    passes = _Passes()
    q = _SyncPassQueue(passes)
    await q.stop()
    await asyncio.wait_for(q.request(**_full()), timeout=5)
    await _settle()
    assert passes.calls == []


@pytest.mark.asyncio
async def test_end_line_counts_requests(records):
    async with _queue() as (q, passes):
        first = asyncio.create_task(q.request(**_full()))
        await passes.started(1)
        rest = [asyncio.create_task(q.request(**_full())) for _ in range(3)]
        await _settle()
        passes.release(0)
        await passes.started(2)
        passes.release(1)
        await asyncio.wait_for(asyncio.gather(first, *rest), timeout=5)

        ends = [
            r
            for r in records
            if r["level"].name == "INFO" and _END_LINE in r["message"]
        ]
        assert len(ends) == 2
        assert [r["extra"]["requests"] for r in ends] == [1, 3]
        assert all("ended after" in r["message"] for r in ends)


@pytest.mark.asyncio
async def test_a_request_after_the_queue_went_idle_starts_a_new_pass():
    async with _queue() as (q, passes):
        first = asyncio.create_task(q.request(**_full()))
        await passes.started(1)
        passes.release(0)
        await asyncio.wait_for(first, timeout=5)
        await _settle()

        second = asyncio.create_task(q.request(**_full()))
        await passes.started(2)
        passes.release(1)
        await asyncio.wait_for(second, timeout=5)
        assert len(passes.calls) == 2
