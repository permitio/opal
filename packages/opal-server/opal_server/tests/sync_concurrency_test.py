import asyncio

import pytest

from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import GitPolicyFetcher


def test_sync_concurrency_default():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_SYNC_CONCURRENCY == 10


@pytest.mark.asyncio
async def test_source_lock_is_stable_per_source(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repo_locks", {})
    lock_a1 = GitPolicyFetcher.source_lock("src-a")
    lock_a2 = GitPolicyFetcher.source_lock("src-a")
    lock_b = GitPolicyFetcher.source_lock("src-b")
    assert lock_a1 is lock_a2  # same source -> same lock object
    assert lock_a1 is not lock_b
    assert isinstance(lock_a1, asyncio.Lock)
