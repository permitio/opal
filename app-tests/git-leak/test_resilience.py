import time

import pytest
import requests
from helpers import (
    HEALTHY_PROBE_REPO,
    bounce_postgres,
    gitea_repo_url,
    list_seeded_repos,
    make_repo_unreachable,
    worker_pids,
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


@pytest.mark.timeout(420)
def test_server_recovers_after_postgres_bounce(opal_multiworker, repo_count):
    """A transient Postgres (broadcaster) outage must reconnect *in place*.

    Runs **2 workers** (via the ``opal_multiworker`` fixture) so the Postgres
    backbone is actually exercised: cross-worker fan-out only happens with >=2
    workers (references/debug-pubsub.md §3-4). A single worker fans out
    in-process and never touches the backbone, so it can't tell #915's in-place
    reconnect from a plain worker respawn — which is why the previous
    single-worker version of this test passed either way.

    Guards PER-15065 (#915): on a backbone disconnect the reconnecting
    broadcaster recovers the reader in process (retry-forever by default), so the
    worker keeps its PID. Before that fix the disconnect escalated to a graceful
    worker shutdown and gunicorn respawned the worker with a *new* PID. We assert
    (a) the worker PIDs are unchanged across the bounce — the in-place-reconnect
    signal — and (b) a scope PUT after the bounce becomes servable, proving the
    broadcast/sync path itself recovered (not just HTTP liveness).
    """
    opal = opal_multiworker

    before = worker_pids()
    assert (
        len(before) == 2
    ), f"expected 2 gunicorn workers for this test, got {sorted(before)}"

    bounce_postgres(down_seconds=5)

    # HTTP must come back first. A respawn would also satisfy this — hence the
    # PID check below, which a respawn would *not* satisfy.
    deadline = time.time() + 90
    recovered = False
    while time.time() < deadline:
        try:
            opal.wait_healthy(timeout=5)
            recovered = True
            break
        except (requests.RequestException, RuntimeError):
            # RequestException: HTTP not back yet; RuntimeError: wait_healthy timed out
            time.sleep(2)
    assert recovered, "server did not recover HTTP within 90s of a postgres bounce"

    # (a) in-place reconnect: the workers must be the *same* processes. A changed
    # PID means the broadcaster gave up and gunicorn respawned the worker — the
    # pre-#915 behavior this guards against.
    after = worker_pids()
    assert after == before, (
        f"workers respawned across the bounce ({sorted(before)} -> {sorted(after)}); "
        f"the broadcaster did not reconnect in place (PER-15065 regressed)"
    )

    # (b) the broadcast/sync path recovered: a freshly PUT scope must become
    # servable. A 200 from its bundle proves the leader received the sync and
    # cloned the repo after the backbone returned. We assert on a served bundle
    # rather than /internal cache counts, which are per-process and so not
    # deterministic to read on a 2-worker stack.
    healthy = list_seeded_repos(1)[0]
    opal.put_scope("post-bounce", gitea_repo_url(healthy))
    served = False
    last = None
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            resp = opal.get_scope_policy("post-bounce")
            last = resp.status_code
            if resp.status_code == 200:
                served = True
                break
        except requests.RequestException as exc:
            last = repr(exc)
        time.sleep(2)
    assert served, (
        f"scope PUT after the bounce never became servable (last: {last}); "
        f"the broadcaster/sync path did not recover"
    )
