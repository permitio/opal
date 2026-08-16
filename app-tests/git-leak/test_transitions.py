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
    """Seeded random put/refresh churn with end-of-round deletes; invariants
    must hold at every settle point. Replay a failure with
    CHURN_SEED=<printed>.

    One deliberate constraint remains: 'repoint' ops are EXCLUDED — a repoint
    orphans the old source's cache entries by design today (the red repoint
    gate covers it: test_scope_repoint_releases_old_repo_cache and
    test_repoint_during_inflight_fetch_drains_old_source). A `put` on a live
    scope therefore reuses that scope's existing repo.

    The delete-vs-inflight-sync exclusion is LIFTED: deletes used to run only
    after every live scope had settled, because a DELETE racing an in-flight
    sync lost its purge (the sync re-populated the caches for the dead scope;
    proven deterministically by seed 309006536 during this test's
    development). PR3's fleet-wide purge channel closes that race, so deletes
    now fire without waiting for the round's live scopes to settle first.
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
        # deletes race in-flight syncs: PR3's fleet purge closes this class,
        # so each live scope has a coin-flip chance to go without waiting for
        # it to settle first.
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
# I3/I4 were exempted here while the docstring already claimed the gate was
# green — exempting exactly the invariants the purge under test exists to
# satisfy. Measured on this head: all three of these gates pass with I3/I4
# enforced, so the exemptions were stale and are gone. I1 stays: a delete or
# repoint that races a hung clone still leaves the DIR on disk (nothing
# reconciles in this PR — PER-15612), which is the documented trade, not a
# memory leak.
@pytest.mark.invariant_exempt("I1")
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
@pytest.mark.invariant_exempt("I1")
def test_delete_during_hung_fetch_returns_bounded(opal):
    """Gate for PR3's fetch timeout; green since it landed.

    Without it the purge waits on the repo lock, and a hung clone holds
    that lock indefinitely, so the DELETE hangs with it.
    """
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
@pytest.mark.invariant_exempt("I1")
def test_repoint_during_inflight_fetch_drains_old_source(opal, repo_count):
    """Gate for PR3's update-path purge; green since it landed.

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
    """Gate for PR3's fleet-wide broadcast purge; green since it landed.
    Without it cache purges are process-local, so any worker whose caches were
    populated by something other than the DELETE it serves leaks permanently.

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


@pytest.mark.timeout(600)
# I2/I3/I4, and I1 deliberately ENFORCED — the reverse of what this carried
# before. The previous marker exempted I1 on the theory that earlier tests leave
# orphan dirs; that reason cannot apply, because opal_multiworker force-recreates
# opal_server and its clone tree is container-local (no volume at /opal), so the
# recreate wipes it. Measured: disk is EMPTY at teardown and I1 holds — this test
# is precisely the one that proves the floor reclaims the dir, so exempting I1
# would have suppressed its own gate.
#
# What legitimately does NOT hold is the MEMORY side. The test stops Postgres,
# so the leader's confirmation cannot cross to the other worker, and that
# worker's cache entries survive by construction — that IS the scenario under
# test. /internal/...-stats answers from whichever worker serves it, so whether
# the violation is observed is a coin flip; without these three the test passes
# or fails on which worker replies, which is how the wrong marker survived two
# green runs before failing.
@pytest.mark.invariant_exempt("I2", "I3", "I4")
def test_delete_reclaims_clone_when_the_purge_broadcast_is_lost(
    opal_multiworker, repo_count
):
    """Gate for the local delete floor.

    Master's ``delete_scope`` removed the clone dir INLINE in the process
    serving the DELETE, depending on no broadcast at all. PR3 replaced that with
    a publish on ``SCOPES_PURGE_CHANNEL``, which is droppable: the DELETE usually
    lands on a non-leader worker and must traverse the broadcaster, and that
    channel is freeze-exempt, so during a backbone gap the publish is *attempted
    and lost* rather than deferred and replayed. With nothing else reclaiming
    (the reconciliation sweep is split out, PER-15612), the dir would then
    survive restart, redeploy and leader failover.

    This is the only test in the bed that measures the floor: every other delete
    path here runs with a healthy backbone, where the confirmation arrives and
    the floor's contribution is invisible.

    ATTRIBUTION. An earlier version of this docstring claimed the leader's purge
    would otherwise have removed the dir. That was true when written and is not
    now: the leader's disk role was cut out of this PR (PER-15612), so the floor
    is the ONLY path in the server that removes a clone dir. Nothing else can
    satisfy this assertion, which is what makes it a gate rather than a
    coincidence.

    Runs 2 workers so the backbone is genuinely in the path (a single worker
    fans out in-process and never touches Postgres).

    Measured both ways when the floor still had competition, against the
    pre-cut code: with the floor, 0 dirs left; with the floor removed, 4 of 6
    survived — the other 2 were DELETEs that happened to land on the leader,
    where publish() reaches the local subscriber before the dead backbone. Post
    cut, none would survive removal of the floor.
    """
    import requests
    from helpers import bounce_postgres
    from invariants import clone_dirs

    opal = opal_multiworker
    n = min(repo_count, 6)

    baseline = clone_dirs()
    for i, repo in enumerate(list_seeded_repos(n)):
        opal.put_scope(f"lost-{i}", gitea_repo_url(repo))

    assert wait_until(
        lambda: len(clone_dirs() - baseline) >= n, timeout=600
    ), f"clones never appeared on disk: {clone_dirs() - baseline}"
    ours = clone_dirs() - baseline

    def _delete_during_the_outage():
        for i in range(n):
            # A 5xx is EXPECTED and not a failure of this test: the fleet purge
            # publish is attempted against a dead backbone and raises, so the
            # caller is correctly NOT told the fleet purge succeeded. The record
            # delete and the local floor both still run — the floor is scheduled
            # before the publish precisely so this case reaches it.
            requests.delete(f"{opal.base_url}/scopes/lost-{i}", timeout=60)

    bounce_postgres(down_seconds=10, during=_delete_during_the_outage)

    assert wait_until(lambda: not (clone_dirs() & ours), timeout=180), (
        "clone dirs survived deletes whose purge broadcast was lost — the local "
        f"floor never ran: still on disk {sorted(clone_dirs() & ours)}"
    )
