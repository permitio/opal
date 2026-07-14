"""Transition tests: interleavings the end-state gates never drive.

See docs/superpowers/specs/2026-07-13-scope-fetcher-lifecycle-tests-design.md.
"""
import time

import pytest
from helpers import (
    compose,
    gitea_repo_url,
    list_seeded_repos,
    make_repo_unreachable,
    wait_until,
    worker_pids,
)
from invariants import clone_dirs, live_source_ids, source_id


@pytest.mark.timeout(900)
def test_delete_recreate_storm(opal, repo_count):
    """Rapid delete/re-create of the same source must serialize on the repo
    lock (lock re-mint path) and end with clean caches.

    Guards 89e090be.
    """
    url = gitea_repo_url(list_seeded_repos(1)[0])
    for i in range(5):
        opal.put_scope("storm", url)
        assert wait_until(
            lambda: opal.get_scope_policy("storm").status_code == 200, timeout=300
        ), f"round {i}: recreated scope never served"
        opal.delete_scope("storm")
    assert wait_until(
        lambda: opal.stats(samples=1)["repo_locks"] == 0, timeout=60
    ), f"caches did not drain after the storm: {opal.stats()}"


@pytest.mark.timeout(1200)
def test_randomized_churn_holds_invariants(opal, repo_count):
    """Seeded random put/refresh churn with settled deletes; invariants must
    hold at every settle point. Replay a failure with CHURN_SEED=<printed>.

    Two deliberate constraints, both lifted when PR3's fleet purge lands
    (no silent caps):
    - 'repoint' ops are EXCLUDED: a repoint orphans the old source's cache
      entries by design today (the red repoint gate covers it). A `put` on a
      live scope therefore reuses that scope's existing repo.
    - Deletes run only at round END, after every live scope has settled: a
      DELETE racing an in-flight sync loses its purge (the sync re-populates
      the caches for the dead scope — same PR3 class; proven deterministically
      by seed 309006536 during this test's development; deterministic red-gate
      coverage lands in test_repoint_during_inflight_fetch_drains_old_source).
      A bounded residual window remains (a served scope's re-sync can still be
      in flight); in practice the settle polling latency dwarfs a tiny repo's
      sync time.
    """
    import os
    import random

    seed = int(os.environ.get("CHURN_SEED", "0")) or random.randrange(1, 2**31)
    print(f"\nCHURN_SEED={seed}")
    rng = random.Random(seed)
    repos = list_seeded_repos(min(repo_count, 6))
    live = {}

    for round_no in range(4):
        # burst: puts + refreshes only (deletes deferred to round end)
        for _ in range(10):
            op = rng.choice(["put", "refresh"])
            sid_ = f"rand-{rng.randrange(3)}"
            if op == "put":
                repo = live.get(sid_) or rng.choice(repos)
                opal.put_scope(sid_, gitea_repo_url(repo))
                live[sid_] = repo
            else:
                opal.refresh_all()
        # settle every live scope before any delete
        for sid_ in list(live):
            assert wait_until(
                lambda s=sid_: opal.get_scope_policy(s).status_code == 200,
                timeout=300,
            ), f"round {round_no}: live scope {sid_} never settled (seed {seed})"
        # settled deletes: each live scope has a coin-flip chance to go
        for sid_ in list(live):
            if rng.random() < 0.5:
                opal.delete_scope(sid_)
                live.pop(sid_)
        opal.delete_scope(f"ghost-{round_no}")  # delete-missing stays a 204 no-op
        drained = wait_until(
            lambda: opal.stats(samples=1)["repo_locks"]
            <= len({r for r in live.values()}),
            timeout=120,
        )
        assert drained, (
            f"round {round_no}: locks exceed live sources (seed {seed}): "
            f"{opal.stats()}"
        )


@pytest.mark.timeout(900)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1", "I3", "I4")
def test_delete_during_hung_fetch_no_crash(opal):
    """Deleting a scope whose clone is hung must never crash a worker (the use-
    after-free class 89e090be fixed).

    GREEN since that fix.
    """
    import requests as _requests

    pids = worker_pids()
    opal.put_scope("hung-nc", make_repo_unreachable("hung-nc-repo"))
    time.sleep(5)  # let the leader's clone start and block on the blackhole
    try:
        try:
            opal.delete_scope("hung-nc")
        except _requests.RequestException:
            pass  # a slow/blocked DELETE is the OTHER test's concern
        assert (
            worker_pids() == pids
        ), "worker crashed/respawned during delete-vs-hung-fetch"
    finally:
        opal.hard_reset()


@pytest.mark.timeout(900)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1", "I3", "I4")
def test_delete_during_hung_fetch_returns_bounded(opal):
    """RED until PR3 (fetch timeout): the purge waits on the repo lock, and a
    hung clone holds that lock indefinitely, so the DELETE hangs with it."""
    import requests as _requests

    opal.put_scope("hung-b", make_repo_unreachable("hung-b-repo"))
    time.sleep(5)
    try:
        start = time.time()
        resp = _requests.delete(f"{opal.base_url}/scopes/hung-b", timeout=90)
        assert (
            resp.status_code in (200, 204) and time.time() - start < 90
        ), "DELETE of a hung-fetch scope did not return in bounded time"
    finally:
        opal.hard_reset()


@pytest.mark.timeout(900)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1", "I3", "I4")
def test_repoint_during_inflight_fetch_drains_old_source(opal, repo_count):
    """RED until PR3 (update-path purge).

    Repointing a scope while its old source's clone is hung must still
    serve the new source (green half) and eventually drop the old
    source's cache entries (red half).
    """
    repo_b = list_seeded_repos(2)[1]
    old_url = make_repo_unreachable("repoint-hang-repo")
    opal.put_scope("rp", old_url)
    time.sleep(5)  # old source's clone is now in flight, holding its lock
    try:
        opal.put_scope("rp", gitea_repo_url(repo_b))  # repoint while hung
        assert wait_until(
            lambda: opal.get_scope_policy("rp").status_code == 200, timeout=300
        ), "repointed scope never served its new source"

        old_sid = source_id(old_url)

        def _old_entries_gone():
            s = opal.stats(samples=1)
            return (
                old_sid not in s["repo_locks_keys"]
                and old_sid not in s["repos_last_fetched_keys"]
            )

        assert wait_until(_old_entries_gone, timeout=60), (
            f"old source {old_sid[:12]}… cache entries leaked after repoint "
            f"(PR3 update-path purge gate): {opal.stats()}"
        )
    finally:
        opal.hard_reset()


@pytest.mark.timeout(1200)
def test_multiworker_churn_drains_every_worker(opal_multiworker, repo_count):
    """RED until PR3 (broadcast purge): cache purges are process-local, so any
    worker whose caches were populated by something other than the DELETE it
    serves leaks permanently.

    Who populates what: the LEADER accumulates handles/locks via its watcher's
    syncs (scopes/task.py); ANY worker additionally caches a pygit2 handle when
    it serves a policy bundle (make_bundle -> _get_current_branch_head ->
    _get_repo). The purge runs only on whichever worker happens to serve the
    DELETE — every accumulation on a different worker outlives the scope. In
    this test only the leader accumulates (nothing GETs bundles), so the
    leader's retained entries are the observable leak. The HIGH finding from
    the PR2 review, as a gate.
    """
    from helpers import stats_by_pid

    opal = opal_multiworker
    n = min(repo_count, 10)
    for i, repo in enumerate(list_seeded_repos(n)):
        opal.put_scope(f"mw-{i}", gitea_repo_url(repo))
    assert wait_until(
        lambda: any(s["repos"] >= 1 for s in stats_by_pid(opal, attempts=40).values()),
        timeout=600,
    ), "no worker ever populated its repo cache"

    for i in range(n):
        opal.delete_scope(f"mw-{i}")

    def _every_worker_drained():
        snaps = stats_by_pid(opal, min_pids=2, attempts=60)
        return len(snaps) >= 2 and all(
            s["repo_locks"] == 0 and s["repos"] == 0 and s["repos_last_fetched"] == 0
            for s in snaps.values()
        )

    assert wait_until(_every_worker_drained, timeout=120), (
        "a worker kept caches the churn's DELETEs never reached (PR3 gate): "
        f"{ {p: {k: v for k, v in s.items() if isinstance(v, int)} for p, s in stats_by_pid(opal).items()} }"
    )
