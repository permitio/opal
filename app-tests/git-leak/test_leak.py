import time

import pytest
import requests
from helpers import gitea_repo_url, list_seeded_repos


def _wait_until(predicate, timeout=30, interval=0.5):
    """Poll ``predicate`` until true or ``timeout`` elapses.

    The predicates here read ``/internal`` via ``opal.stats()``, which does
    ``raise_for_status()``. A *transient* request error (a momentary 5xx, a
    connection reset, or a read racing an in-flight mutation) is treated as "not
    yet" and retried instead of propagating and turning the whole test into an
    ERROR before the deadline. A *persistent* failure still surfaces: the wait
    just returns ``False`` and the caller's ``assert`` fires with the last stats.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except requests.RequestException:
            pass
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


@pytest.mark.timeout(900)
def test_shared_repo_survives_sibling_scope_delete(opal, repo_count):
    """Deleting one of two scopes that share a repo URL must not purge the
    shared cache entry or break the surviving scope.

    Guards PR2 against *over*-purging: the GitPolicyFetcher caches are keyed by
    repo URL (source_id), not scope_id, and sharing one policy repo across many
    scopes is a normal setup. ``test_churn_releases_caches`` only asserts the
    caches drain when *all* scopes referencing a URL are gone — so a purge that
    fires whenever *any* scope pointing at the URL is deleted would pass that
    gate while breaking every surviving sibling. This is the inverse assertion.

    PASSES on this branch (master never purges, so the entry trivially
    survives); becomes load-bearing the moment PR2's purge lands.
    """
    repo = list_seeded_repos(1)[0]
    url = gitea_repo_url(repo)
    opal.put_scope("shared-a", url)
    opal.put_scope("shared-b", url)

    # both scopes share one URL, so all three caches hold exactly one entry
    locked = _wait_until(lambda: opal.stats()["repo_locks"] >= 1, timeout=600)
    assert locked, f"shared repo never locked: {opal.stats()}"
    opal.refresh_all()
    fetched = _wait_until(lambda: opal.stats()["repos"] >= 1, timeout=600)
    assert fetched, f"refresh never populated the shared repo: {opal.stats()}"

    # sanity: the survivor serves *before* the sibling delete, so a failure
    # after it can only be caused by the delete
    served = _wait_until(
        lambda: opal.get_scope_policy("shared-b").status_code == 200, timeout=120
    )
    assert served, "shared-b never served before the sibling delete"

    opal.delete_scope("shared-a")

    # Give an (incorrect) URL-keyed purge time to fire, then assert the shared
    # entry survived. A fixed sleep — not a wait-for-condition — because the
    # expected outcome is "nothing changes", which has no event to wait on.
    time.sleep(5)
    stats = opal.stats()
    assert stats["repo_locks"] >= 1 and stats["repos"] >= 1, (
        f"deleting scope shared-a purged the cache entry still referenced by "
        f"shared-b (over-purge): {stats}"
    )
    resp = opal.get_scope_policy("shared-b")
    assert resp.status_code == 200, (
        f"shared-b stopped serving after its sibling was deleted "
        f"(status {resp.status_code}) — the shared clone was torn down"
    )


@pytest.mark.timeout(900)
def test_scope_repoint_releases_old_repo_cache(opal, repo_count):
    """Re-pointing a scope to a new repo URL, then deleting it, must drain ALL
    cache entries — including the orphaned old URL's.

    ``PUT /scopes`` is create-or-update, so PUT-ing an existing scope_id with a
    *different* repo URL orphans the old URL's cache entries: the same leak as
    churn, via a path ``test_churn_releases_caches`` (delete-only) never takes.
    A purge hooked solely into scope deletion would look up the scope's
    *current* URL and leave the old entry behind forever.

    FAILS on this branch (without PR2, nothing purges — the same right-reason
    failure as churn); stays red after PR2 unless its purge also covers the
    update path (or sweeps entries no live scope references).
    """
    assert repo_count >= 2, "needs --boot-scopes >= 2"
    repo_a, repo_b = list_seeded_repos(2)

    opal.put_scope("repoint", gitea_repo_url(repo_a))
    locked = _wait_until(lambda: opal.stats()["repo_locks"] >= 1, timeout=600)
    assert locked, f"initial repo never locked: {opal.stats()}"
    opal.refresh_all()
    fetched = _wait_until(lambda: opal.stats()["repos"] >= 1, timeout=600)
    assert fetched, f"refresh never populated the initial repo: {opal.stats()}"

    # Re-point the same scope_id at a different repo; repo_a's entries are now
    # referenced by no scope. The sync triggered by the PUT clones repo_b
    # (filling repo_locks), and the refresh fills its repos /
    # repos_last_fetched — so both URLs are visible in the caches, proof the
    # orphan exists before the delete (this guards the setup, not the leak).
    opal.put_scope("repoint", gitea_repo_url(repo_b))
    locked = _wait_until(lambda: opal.stats()["repo_locks"] >= 2, timeout=600)
    assert locked, f"re-pointed repo never locked: {opal.stats()}"
    opal.refresh_all()
    fetched = _wait_until(lambda: opal.stats()["repos"] >= 2, timeout=600)
    assert fetched, (
        f"expected cache entries for both the old and new URL after the "
        f"re-point: {opal.stats()}"
    )

    opal.delete_scope("repoint")

    def _all_caches_empty() -> bool:
        s = opal.stats(samples=1)
        return s["repo_locks"] == 0 and s["repos"] == 0 and s["repos_last_fetched"] == 0

    released = _wait_until(_all_caches_empty, timeout=60)
    assert released, (
        f"caches did not drain after deleting the re-pointed scope (the old "
        f"URL's orphaned entry leaks unless the purge covers updates too): "
        f"{opal.stats()}"
    )
