"""Start-state tests: what the server boots INTO (S2-S7 in the design spec).

The cold-empty start (S1) is covered by test_boot.py.
"""
import time

import pytest
from helpers import (
    HEALTHY_PROBE_REPO,
    compose,
    gitea_repo_url,
    list_seeded_repos,
    make_repo_unreachable,
    wait_until,
)
from invariants import clone_dirs


def _clone_log_count() -> int:
    return compose("logs", "--no-log-prefix", "opal_server").stdout.count(
        "Cloning repo"
    )


@pytest.mark.timeout(900)
@pytest.mark.allow_worker_restart
def test_warm_boot_reuses_clones(opal, repo_count):
    """A restart with intact clones must serve without re-cloning (S2)."""
    n = min(repo_count, 10)
    for i, repo in enumerate(list_seeded_repos(n)):
        opal.put_scope(f"warm-{i}", gitea_repo_url(repo))
    for i in range(n):
        assert wait_until(
            lambda i=i: opal.get_scope_policy(f"warm-{i}").status_code == 200,
            timeout=600,
        ), f"warm-{i} never served before the restart"

    clones_before = _clone_log_count()
    compose("restart", "opal_server")
    opal.wait_healthy()

    for i in range(n):
        assert wait_until(
            lambda i=i: opal.get_scope_policy(f"warm-{i}").status_code == 200,
            timeout=300,
        ), f"warm-{i} not served after warm restart"
    assert (
        _clone_log_count() == clones_before
    ), "warm boot re-cloned instead of reusing the on-disk clones"
