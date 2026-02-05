import asyncio
import time

import pytest
from opal_common.async_utils import run_sync_with_timeout


@pytest.mark.asyncio
async def test_run_sync_with_timeout_completes_normally():
    """A fast function should complete within the timeout."""

    def fast_func(x, y):
        return x + y

    result = await run_sync_with_timeout(fast_func, 2, 3, timeout=5.0)
    assert result == 5


@pytest.mark.asyncio
async def test_run_sync_with_timeout_raises_on_slow_function():
    """A slow function should raise asyncio.TimeoutError when it exceeds the timeout."""

    def slow_func():
        time.sleep(10)
        return "done"

    with pytest.raises(asyncio.TimeoutError):
        await run_sync_with_timeout(slow_func, timeout=0.3)


@pytest.mark.asyncio
async def test_run_sync_with_timeout_no_timeout_when_zero():
    """When timeout is 0, no timeout should be applied (behaves like run_sync)."""

    def quick_func():
        return 42

    result = await run_sync_with_timeout(quick_func, timeout=0)
    assert result == 42


@pytest.mark.asyncio
async def test_run_sync_with_timeout_no_timeout_when_none():
    """When timeout is None, no timeout should be applied (behaves like run_sync)."""

    def quick_func():
        return "ok"

    result = await run_sync_with_timeout(quick_func, timeout=None)
    assert result == "ok"


@pytest.mark.asyncio
async def test_run_sync_with_timeout_propagates_exceptions():
    """Exceptions from the wrapped function should propagate normally."""

    def failing_func():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        await run_sync_with_timeout(failing_func, timeout=5.0)
