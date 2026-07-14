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
