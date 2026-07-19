import asyncio

import pytest
from opal_server.config import OpalServerConfig
from opal_server.git_fetcher import GitPolicyFetcher, _mark_git_op_started, _mark_git_op_done
from opal_server.scopes.purge import (
    ScopePurgeCommand,
    handle_purge_message,
    purge_local_memory,
    subscribe_worker_purge_handler,
)


def test_purge_channel_config_default():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_PURGE_CHANNEL == "__opal_scope_purge__"


@pytest.fixture(autouse=True)
def clear_caches():
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    yield
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()


def _cmd(sid="sid-1", path="/clones/sid-1"):
    return ScopePurgeCommand(
        source_id=sid, clone_path=path, scope_id="s1", reason="delete"
    )


def test_purge_local_memory_pops_repo_and_timestamp_but_never_locks():
    GitPolicyFetcher.repos["/clones/sid-1"] = object()
    GitPolicyFetcher.repos_last_fetched["sid-1"] = "ts"
    lock = asyncio.Lock()
    GitPolicyFetcher.repo_locks["sid-1"] = lock

    purge_local_memory("sid-1", "/clones/sid-1")

    assert "/clones/sid-1" not in GitPolicyFetcher.repos
    assert "sid-1" not in GitPolicyFetcher.repos_last_fetched
    # Lock-identity invariant: only lock holders may pop repo_locks.
    assert GitPolicyFetcher.repo_locks["sid-1"] is lock


def test_purge_local_memory_skips_forget_repo_while_git_op_in_flight():
    """Freeing a pygit2 handle while a pool thread still uses it is a crash
    risk — the handle must survive; the timestamp pop is still safe."""
    GitPolicyFetcher.repos["/clones/sid-1"] = object()
    GitPolicyFetcher.repos_last_fetched["sid-1"] = "ts"
    _mark_git_op_started("sid-1")
    try:
        purge_local_memory("sid-1", "/clones/sid-1")
    finally:
        _mark_git_op_done("sid-1")

    assert "/clones/sid-1" in GitPolicyFetcher.repos  # handle survived
    assert "sid-1" not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_handle_purge_message_parses_and_purges():
    GitPolicyFetcher.repos["/clones/sid-1"] = object()
    GitPolicyFetcher.repos_last_fetched["sid-1"] = "ts"

    await handle_purge_message(None, _cmd().dict())

    assert "/clones/sid-1" not in GitPolicyFetcher.repos
    assert "sid-1" not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_handle_purge_message_tolerates_garbage_payload():
    # Must not raise — a bad message must never kill the subscription.
    await handle_purge_message(None, {"nonsense": True})
    await handle_purge_message(None, None)
    await handle_purge_message(None, "not-a-dict")


@pytest.mark.asyncio
async def test_subscribe_worker_purge_handler_wires_channel():
    class FakeEndpoint:
        def __init__(self):
            self.subs = []

        async def subscribe(self, topics, callback):
            self.subs.append((list(topics), callback))

    ep = FakeEndpoint()
    await subscribe_worker_purge_handler(ep)
    assert ep.subs == [(["__opal_scope_purge__"], handle_purge_message)]
