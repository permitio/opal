import time

import pytest

from helpers import (
    bounce_postgres,
    gitea_repo_url,
    list_seeded_repos,
    make_repo_unreachable,
)


@pytest.mark.timeout(300)
def test_offline_repo_does_not_block_healthy_scopes(opal, repo_count):
    """An unreachable repo must not stop healthy scopes from serving.

    FAILS on master: the scopes path has no fetch timeout, so a hung
    clone occupies the shared executor and the server stalls.
    """
    # a routable-but-dead address (TEST-NET-1, RFC 5737): the clone hangs
    opal.put_scope("offline", make_repo_unreachable("dead-repo"), branch="main")

    healthy = list_seeded_repos(1)[0]
    opal.put_scope("healthy", gitea_repo_url(healthy))

    # the healthy scope's repo must appear in the cache within a bounded time,
    # even though the offline scope is hanging
    deadline = time.time() + 60
    served = False
    while time.time() < deadline:
        if opal.stats()["repos"] >= 1:
            served = True
            break
        time.sleep(2)
    assert served, "healthy scope never loaded while an offline repo was hanging"


@pytest.mark.timeout(300)
def test_server_recovers_after_postgres_bounce(opal):
    """A transient Postgres (broadcaster) outage must not leave the server down.

    Recovery guard, not a known-broken case. On current master this PASSES:
    when the broadcast channel drops, the affected worker triggers a graceful
    shutdown and gunicorn respawns it, while the sibling worker keeps serving
    HTTP — so the surface recovers within the window. It guards against a
    regression of that property (PER-15065's in-process reconnect would make
    recovery cleaner by avoiding the worker churn, but recovery already holds).
    """
    assert opal.stats()  # healthy before
    bounce_postgres(down_seconds=5)

    deadline = time.time() + 60
    recovered = False
    while time.time() < deadline:
        try:
            opal.wait_healthy(timeout=5)
            opal.stats()
            recovered = True
            break
        except Exception:
            time.sleep(2)
    assert recovered, "server did not recover within 60s of a postgres bounce"
