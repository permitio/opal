import time

import pytest
from opal_server.config import opal_server_config
from opal_server.git_fetcher import run_in_git_executor


@pytest.mark.asyncio
async def test_hanging_git_op_raises_timeout(monkeypatch):
    """A clone/fetch that hangs must surface TimeoutError, not block
    forever."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)

    def _hang():
        # Short enough that the lingering pool thread doesn't delay teardown,
        # but well above the 0.2s timeout under test.
        time.sleep(1)

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        await run_in_git_executor(
            _hang, timeout=opal_server_config.SCOPES_GIT_FETCH_TIMEOUT
        )
    assert time.monotonic() - start < 2, "wait_for did not unblock promptly"
