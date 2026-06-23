import os
import time

import pytest

from helpers import compose, gitea_repo_url, list_seeded_repos


@pytest.mark.timeout(2400)
def test_boot_loads_all_scopes(opal, repo_count):
    """Measure how long a fresh boot takes to load all scope repos.

    On master this is serial and slow (the ~20-min problem at scale).
    PR4 tightens BOOT_TARGET_SECONDS to assert the parallel speedup.
    """
    n = repo_count
    repos = list_seeded_repos(n)
    for i, name in enumerate(repos):
        opal.put_scope(f"boot-{i}", gitea_repo_url(name))

    # restart only the server so it re-runs sync_scopes on boot
    compose("restart", "opal_server")
    opal.wait_healthy(timeout=600)

    start = time.time()
    deadline = start + 2000
    while time.time() < deadline:
        if opal.stats()["repos"] >= n:
            break
        time.sleep(2)
    elapsed = time.time() - start

    # PR1 records the baseline (loose). PR4 will set BOOT_TARGET_SECONDS low.
    BOOT_TARGET_SECONDS = int(os.environ.get("BOOT_TARGET_SECONDS", "2000"))
    print(f"boot loaded {n} scopes in {elapsed:.1f}s (target {BOOT_TARGET_SECONDS}s)")
    assert opal.stats()["repos"] >= n, "not all scopes loaded after boot"
    assert elapsed < BOOT_TARGET_SECONDS, f"boot too slow: {elapsed:.1f}s"
