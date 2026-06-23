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


@pytest.mark.timeout(900)
def test_churn_releases_caches(opal, repo_count):
    """Create then delete many scopes; the three caches must return to empty.

    FAILS on master: delete_scope never purges GitPolicyFetcher caches.
    """
    n = min(repo_count, 100)
    repos = list_seeded_repos(n)
    for i, name in enumerate(repos):
        opal.put_scope(f"churn-{i}", gitea_repo_url(name))
    loaded = _wait_until(lambda: opal.stats()["repos"] >= n, timeout=600)
    assert loaded, f"initial load never reached {n} repos: {opal.stats()}"

    for i in range(n):
        opal.delete_scope(f"churn-{i}")

    released = _wait_until(lambda: opal.stats()["repos"] == 0, timeout=30)
    stats = opal.stats()
    assert released, f"repos cache did not drain: {stats}"
    assert stats["repos_last_fetched"] == 0, stats


@pytest.mark.timeout(900)
def test_repeat_sync_does_not_grow(opal, repo_count):
    """Re-syncing the *same* scopes must not grow the caches.

    Idempotency guard, not a known-broken case. On current master this
    PASSES: a clone path is keyed by the repo URL (``source_id`` =
    sha256(url)+branch-shard), so re-syncing identical scopes reuses the
    existing ``repos`` / ``repos_last_fetched`` entries instead of
    allocating new ones. It guards against a regression that would make
    repeat sync allocate per-sync. The unbounded *growth + no purge on
    delete* leak is covered by ``test_churn_releases_caches`` above, which
    uses distinct scopes and DOES fail on master.
    """
    n = min(repo_count, 50)
    repos = list_seeded_repos(n)
    for i, name in enumerate(repos):
        opal.put_scope(f"stable-{i}", gitea_repo_url(name))
    loaded = _wait_until(lambda: opal.stats()["repos"] >= n, timeout=600)
    assert loaded, f"initial sync never reached {n} repos: {opal.stats()}"

    baseline = opal.stats()["repos"]
    for _ in range(10):
        opal.refresh_all()
        time.sleep(2)

    grown = opal.stats()["repos"]
    assert grown <= baseline, f"repos cache grew on repeat sync: {baseline} -> {grown}"
