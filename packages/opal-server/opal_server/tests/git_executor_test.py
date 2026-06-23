import time

import pytest

from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import run_in_git_executor


def test_git_resilience_config_defaults():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_GIT_FETCH_TIMEOUT == 120.0
    assert clean.SCOPES_GIT_MAX_WORKERS == 10


@pytest.mark.asyncio
async def test_run_in_git_executor_returns_value():
    result = await run_in_git_executor(lambda: 21 * 2, timeout=5)
    assert result == 42


@pytest.mark.asyncio
async def test_run_in_git_executor_times_out():
    with pytest.raises(TimeoutError):
        await run_in_git_executor(lambda: time.sleep(2), timeout=0.1)


@pytest.mark.asyncio
async def test_zero_timeout_means_no_limit():
    result = await run_in_git_executor(lambda: "ok", timeout=0)
    assert result == "ok"
