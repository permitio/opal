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
    _wait_until(lambda: opal.stats()["repos"] >= n, timeout=600)

    for i in range(n):
        opal.delete_scope(f"churn-{i}")

    released = _wait_until(lambda: opal.stats()["repos"] == 0, timeout=30)
    stats = opal.stats()
    assert released, f"repos cache did not drain: {stats}"
    assert stats["repos_last_fetched"] == 0, stats


@pytest.mark.timeout(900)
def test_repeat_sync_does_not_grow(opal, repo_count):
    """Re-syncing the same scopes must not grow the caches unboundedly.

    FAILS on master: repos cache only ever grows.
    """
    n = min(repo_count, 50)
    repos = list_seeded_repos(n)
    for i, name in enumerate(repos):
        opal.put_scope(f"stable-{i}", gitea_repo_url(name))
    _wait_until(lambda: opal.stats()["repos"] >= n, timeout=600)

    baseline = opal.stats()["repos"]
    for _ in range(10):
        opal.refresh_all()
        time.sleep(2)

    grown = opal.stats()["repos"]
    assert grown <= baseline, f"repos cache grew on repeat sync: {baseline} -> {grown}"
