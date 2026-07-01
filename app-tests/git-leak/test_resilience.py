import time

import pytest
import requests
from helpers import (
    HEALTHY_PROBE_REPO,
    bounce_postgres,
    gitea_repo_url,
    list_seeded_repos,
    make_repo_unreachable,
)

# Enough hanging clones to exhaust opal's default fetch executor
# (run_sync -> run_in_executor(None, ...), a ThreadPoolExecutor of
# min(32, cpu+4) workers). One hang wouldn't starve a multi-thread pool, so we
# saturate it with many; after PR3's fetch timeout these give up and free their
# threads, letting the healthy scope through.
OFFLINE_REPOS = 40


@pytest.mark.timeout(420)
def test_offline_repo_does_not_block_healthy_scopes(opal, repo_count):
    """Unreachable repos must not stop a healthy scope from serving.

    FAILS on this branch (without PR3): the scopes path has no fetch
    timeout, so the hung clones of the offline repos occupy the shared
    fetch executor and the healthy scope's bundle never becomes
    available.
    """
    # the `blackhole` sidecar accepts the TCP handshake then never answers, so
    # each of these clones hangs (holding a fetch-executor thread) rather than
    # failing fast; enough of them saturate the pool.
    for i in range(OFFLINE_REPOS):
        opal.put_scope(
            f"offline-{i}", make_repo_unreachable(f"dead-{i}"), branch="main"
        )

    # Point the healthy scope at a repo *no other test clones* (HEALTHY_PROBE_REPO
    # is seeded outside the numeric range the boot/leak tests enumerate). Clones
    # survive compose restart/stop/start, so reusing a shared seeded repo here
    # would let this scope hit the existing on-disk clone via _discover_repository,
    # skip _clone(), and serve 200 without ever touching the saturated executor —
    # false-passing this gate. A never-cloned repo forces a real clone through the
    # starved pool, so the gate fails correctly on this branch (no PR3 timeout).
    opal.put_scope("healthy", gitea_repo_url(HEALTHY_PROBE_REPO))

    try:
        # The healthy scope must become *servable* within a bounded time even
        # while the offline scopes hang. A 200 from its policy bundle proves the
        # clone completed and the scope is served — a stronger signal than a
        # cache count, and exactly what the offline hang starves on master.
        #
        # A 200 here can't be a *masked* default bundle: GET /{scope}/policy
        # falls back to the "default" scope on a bad/missing repo, but this bed
        # never creates a "default" scope, so that fallback raises instead of
        # returning 200. The only way to get 200 is the healthy clone completing.
        deadline = time.time() + 90
        served = False
        last = None
        while time.time() < deadline:
            try:
                resp = opal.get_scope_policy("healthy")
                last = resp.status_code
                if resp.status_code == 200:
                    served = True
                    break
            except requests.RequestException as exc:  # may stall when starved
                last = repr(exc)
            time.sleep(2)
        assert served, (
            f"healthy scope never served while {OFFLINE_REPOS} offline repos "
            f"were hanging (last policy response: {last})"
        )
    finally:
        # The offline clones hang for the blackhole's full duration, occupying
        # executor threads. On the session-scoped stack that would starve every
        # later test, and per-scope DELETEs would queue behind the hung threads.
        # hard_reset stops the server (killing the hung threads), flushes the
        # Redis scope store so preload doesn't re-clone them, and restarts clean.
        opal.hard_reset()


@pytest.mark.timeout(300)
def test_server_recovers_after_postgres_bounce(opal, repo_count):
    """A transient Postgres (broadcaster) outage must not break propagation.

    Recovery guard, not a known-broken case — PASSES on this branch: when the
    broadcast channel drops, the affected worker triggers a graceful shutdown
    and gunicorn respawns it, and once Postgres is back the broadcaster
    reconnects. We prove recovery of the *broadcast path*, not just HTTP
    liveness: after the bounce we PUT a fresh scope and assert it actually
    syncs (its repo lands in the cache), which only happens if the leader
    received the sync notification over the recovered broadcaster.
    (PER-15065's in-process reconnect would make recovery cleaner by avoiding
    the worker churn, but recovery already holds.)
    """
    baseline = opal.stats()  # healthy before
    assert baseline
    baseline_locks = baseline["repo_locks"]

    bounce_postgres(down_seconds=5)

    # wait for the HTTP surface to come back first
    deadline = time.time() + 90
    recovered = False
    while time.time() < deadline:
        try:
            opal.wait_healthy(timeout=5)
            opal.stats()
            recovered = True
            break
        except (requests.RequestException, RuntimeError):
            # RequestException: HTTP not back yet; RuntimeError: wait_healthy timed out
            time.sleep(2)
    assert recovered, "server did not recover HTTP within 90s of a postgres bounce"

    # prove the broadcast path itself recovered: a freshly PUT scope must sync
    healthy = list_seeded_repos(1)[0]
    opal.put_scope("post-bounce", gitea_repo_url(healthy))
    synced = False
    deadline = time.time() + 120
    while time.time() < deadline:
        if opal.stats()["repo_locks"] > baseline_locks:
            synced = True
            break
        time.sleep(2)
    assert (
        synced
    ), "scope PUT after the bounce never synced; broadcaster did not recover"
