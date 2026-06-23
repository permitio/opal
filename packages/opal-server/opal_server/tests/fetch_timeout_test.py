import time

import pytest

from opal_server.config import opal_server_config
from opal_server.git_fetcher import run_in_git_executor


@pytest.mark.asyncio
async def test_hanging_git_op_raises_timeout(monkeypatch):
    """A clone/fetch that hangs must surface TimeoutError, not block forever."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)

    def _hang():
        time.sleep(5)

    start = time.time()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            _hang, timeout=opal_server_config.SCOPES_GIT_FETCH_TIMEOUT
        )
    assert time.time() - start < 2, "wait_for did not unblock promptly"
