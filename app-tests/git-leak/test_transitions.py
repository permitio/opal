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
