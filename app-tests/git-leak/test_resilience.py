import time

import pytest
import requests
from helpers import (
    HEALTHY_PROBE_REPO,
    bounce_postgres,
    broadcaster_connect_count,
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


def _wait_served(opal, scope_id: str, timeout: int):
    """Poll a scope's policy bundle until it serves 200 or ``timeout`` elapses.

    Returns ``(served, last)`` where ``last`` is the final status code or
    exception repr, for the caller's assertion message.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            resp = opal.get_scope_policy(scope_id)
            last = resp.status_code
            if resp.status_code == 200:
                return True, last
        except requests.RequestException as exc:
            last = repr(exc)
        time.sleep(2)
    return False, last


@pytest.mark.timeout(420)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1")
def test_offline_repo_does_not_block_healthy_scopes(opal, repo_count):
    """Unreachable repos must not stop a healthy scope from serving.

    FAILS on this branch (without PR3): the scopes path has no fetch
    timeout, so the hung clones of the offline repos occupy the shared
    fetch executor and the healthy scope's bundle never becomes
    available.
    """
    try:
        # the `blackhole` sidecar accepts the TCP handshake then never answers, so
        # each of these clones hangs (holding a fetch-executor thread) rather than
        # failing fast; enough of them saturate the pool. These PUTs live *inside*
        # the try so that if one fails partway through, the finally still runs
        # hard_reset() — otherwise the clones already dispatched to the executor
        # would hang for the blackhole's full duration and starve the
        # session-scoped stack for every later test.
        for i in range(OFFLINE_REPOS):
            opal.put_scope(
                f"offline-{i}", make_repo_unreachable(f"dead-{i}"), branch="main"
            )

        # Point the healthy scope at a repo *no other test clones*
        # (HEALTHY_PROBE_REPO is seeded outside the numeric range the boot/leak
        # tests enumerate) so it must perform a genuine clone rather than reuse a
        # surviving on-disk clone via _discover_repository. Serving the bundle
        # shares the same starved executor too, so a shared repo would also stay
        # red here — the never-cloned probe additionally guarantees the *clone*
        # itself is exercised through the starved pool (fails correctly on this
        # branch, no PR3 timeout).
        opal.put_scope("healthy", gitea_repo_url(HEALTHY_PROBE_REPO))

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
    signal; (b) the backbone reader actually dropped and reconnected (its connect
    log count increased), so (a) is not vacuously true because the bounce failed
    to break anything; (c) a scope PUT after the bounce becomes servable,
    proving the broadcast/sync path itself recovered (not just HTTP liveness);
    and (d) a scope PUT *during* the outage becomes servable too.

    (d) guards the disconnect-window publish path: the scope PUT publishes its
    sync trigger on the git-webhook topic, which the reconnecting broadcaster
    buffers while the backbone is down and replays on reconnect (and which
    #933's publish freeze explicitly exempts, keeping that behavior after a
    rebase). A 201 acknowledged during the gap must therefore never be silently
    dropped — the scope sits in the store but no resync would ever sync it, so
    only the replayed trigger can make it servable. The during-outage scope uses
    a *different* seeded repo than (c)'s: serving reads the on-disk clone keyed
    by repo URL, so sharing (c)'s repo would let (d) return 200 off the clone
    (c)'s sync produced, without (d)'s own trigger ever being delivered.
    """
    opal = opal_multiworker
    assert repo_count >= 2, "needs --boot-scopes >= 2"
    post_bounce_repo, during_bounce_repo = list_seeded_repos(2)

    before = worker_pids()
    assert (
        len(before) == 2
    ), f"expected 2 gunicorn workers for this test, got {sorted(before)}"
    # baseline reader (re)connect count — assertion (b) requires it to increase
    before_connects = broadcaster_connect_count()

    def _publish_during_outage():
        # A PUT while the backbone is down: scopes.put persists to Redis, and
        # the sync publish is buffered for replay (the broadcaster's outbound
        # buffer catches the failed backbone share rather than raising), so
        # this returns 201 mid-outage. If it ever starts failing here instead,
        # that is a behavior change worth a loud test failure — bounce_postgres
        # restores Postgres before propagating the exception.
        opal.put_scope("during-bounce", gitea_repo_url(during_bounce_repo))

    bounce_postgres(down_seconds=5, during=_publish_during_outage)

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

    # (b) the bounce actually broke and reconnected the backbone reader — so (a)
    # is not vacuously true because nothing dropped. The reconnecting broadcaster
    # logs a fresh connect line on every reconnect; the count must strictly
    # increase over the pre-bounce baseline (poll, since the reconnect lags the
    # Postgres healthcheck by the backoff + resync-settle window).
    deadline = time.time() + 60
    reconnected = False
    after_connects = before_connects
    while time.time() < deadline:
        after_connects = broadcaster_connect_count()
        if after_connects > before_connects:
            reconnected = True
            break
        time.sleep(2)
    assert reconnected, (
        f"broadcaster reader never logged a reconnect after the bounce "
        f"(connect count stayed {before_connects}); the bounce may not have "
        f"dropped the backbone, which would make the PID-unchanged check above "
        f"vacuous"
    )

    # (c) the broadcast/sync path recovered: a freshly PUT scope must become
    # servable. A 200 from its bundle proves the leader received the sync and
    # cloned the repo after the backbone returned. We assert on a served bundle
    # rather than /internal cache counts, which are per-process and so not
    # deterministic to read on a 2-worker stack.
    opal.put_scope("post-bounce", gitea_repo_url(post_bounce_repo))
    served, last = _wait_served(opal, "post-bounce", timeout=120)
    assert served, (
        f"scope PUT after the bounce never became servable (last: {last}); "
        f"the broadcaster/sync path did not recover"
    )

    # (d) the scope acknowledged DURING the outage must become servable: its
    # buffered sync trigger has to be replayed to the leader once the backbone
    # is back. By this point (c) has proven the post-recovery path works, so a
    # failure here isolates the disconnect-window publish being dropped.
    served, last = _wait_served(opal, "during-bounce", timeout=120)
    assert served, (
        f"scope PUT during the bounce never became servable (last: {last}); "
        f"its sync trigger was dropped instead of buffered/replayed across "
        f"the backbone gap"
    )
