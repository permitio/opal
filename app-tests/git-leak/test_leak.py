import time

import pytest
from helpers import gitea_repo_url, list_seeded_repos


def _wait_until(predicate, timeout=30, interval=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _load_scopes(opal, prefix, names):
    """PUT a scope per repo, then force a second sync so all three caches fill.

    The first sync of a fresh scope takes the clone path, which populates only
    ``repo_locks`` — ``repos`` and ``repos_last_fetched`` are filled solely by
    the discover/fetch path on a *subsequent* sync. ``refresh_all()`` triggers
    that second sync, so after this returns all three caches reflect the N
    scopes and the drain assertions test a cache the sync path actually fills.

    Returns the per-key load count reached (max over a wait).
    """
    n = len(names)
    for i, name in enumerate(names):
        opal.put_scope(f"{prefix}-{i}", gitea_repo_url(name))
    # repo_locks is populated on the first sync (the clone path), so it is the
    # deterministic signal that every scope was at least picked up.
    locked = _wait_until(lambda: opal.stats()["repo_locks"] >= n, timeout=600)
    assert locked, f"initial load never locked {n} repos: {opal.stats()}"
    # force the discover/fetch path so `repos` / `repos_last_fetched` fill too
    opal.refresh_all()
    fetched = _wait_until(lambda: opal.stats()["repos"] >= n, timeout=600)
    assert fetched, f"refresh never populated {n} repos: {opal.stats()}"
    return opal.stats()


@pytest.mark.timeout(900)
def test_churn_releases_caches(opal, repo_count):
    """Create then delete many scopes; the three caches must return to empty.

    FAILS on this branch (without PR2): delete_scope never purges the
    GitPolicyFetcher caches, so they stay populated after every scope is
    gone. Becomes green once PR2 lands.
    """
    n = min(repo_count, 100)
    repos = list_seeded_repos(n)
    loaded = _load_scopes(opal, "churn", repos)
    assert loaded["repo_locks"] >= n and loaded["repos"] >= n, loaded
    rss_loaded = loaded["rss_kb"]

    for i in range(n):
        opal.delete_scope(f"churn-{i}")

    # all three caches must drain to empty once every scope is deleted. Read a
    # single stats snapshot per poll so the three keys reflect the same
    # observation (and to avoid 3x the HTTP round-trips per iteration).
    def _all_caches_empty() -> bool:
        s = opal.stats(samples=1)
        return s["repo_locks"] == 0 and s["repos"] == 0 and s["repos_last_fetched"] == 0

    released = _wait_until(_all_caches_empty, timeout=60)
    stats = opal.stats()
    assert released, f"caches did not drain after deleting all scopes: {stats}"

    # The cache drain above is the gate. RSS is only a loose backstop here:
    # freeing the caches need not return memory to the OS (glibc/Python keep
    # arenas), so this guards against a *gross* leak — RSS ballooning well past
    # the loaded peak — without false-failing on allocator slack once PR2 lands.
    rss_budget = rss_loaded + max(100_000, rss_loaded // 2)
    assert stats["rss_kb"] <= rss_budget, (
        f"RSS ballooned across churn: {rss_loaded} -> {stats['rss_kb']} kb "
        f"(budget {rss_budget})"
    )


@pytest.mark.timeout(900)
def test_repeat_sync_rss_stays_bounded(opal, repo_count):
    """Re-syncing the *same* scopes must not leak per-sync memory (RSS guard).

    Deliberately an **RSS** guard, not a cache-count leak gate. The clone caches
    are keyed by repo URL (``source_id`` = sha256(url)+branch-shard), so
    re-syncing identical scopes reuses the existing ``repos`` /
    ``repos_last_fetched`` entries; the cache *counts* cannot grow for *any*
    implementation. A ``len(repos)`` assertion would therefore be tautological
    (it can't fail), so it is intentionally omitted here — do not re-add it as a
    "gate". The load-bearing assertion is RSS: it catches a regression where each
    repeat sync leaks per-sync allocations even while the entry count stays flat.

    The unbounded-growth-then-no-purge-on-delete leak is covered by
    ``test_churn_releases_caches`` above, which uses *distinct* scopes.
    """
    n = min(repo_count, 50)
    repos = list_seeded_repos(n)
    loaded = _load_scopes(opal, "stable", repos)
    baseline_rss = loaded["rss_kb"]

    for _ in range(10):
        opal.refresh_all()
        time.sleep(2)

    grown = opal.stats()
    # allow generous headroom for allocator slack; fail only on a real per-sync
    # leak (10 refreshes of N scopes ballooning RSS).
    rss_budget = baseline_rss + max(50_000, baseline_rss // 5)
    assert grown["rss_kb"] <= rss_budget, (
        f"RSS grew unboundedly on repeat sync: "
        f"{baseline_rss} -> {grown['rss_kb']} kb (budget {rss_budget})"
    )
