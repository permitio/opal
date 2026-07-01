import os
import shutil

import pytest
from helpers import (
    HEALTHY_PROBE_REPO,
    GiteaAdmin,
    OpalServerClient,
    compose,
    list_seeded_repos,
)


def pytest_addoption(parser):
    parser.addoption(
        "--boot-scopes",
        action="store",
        default="50",
        help="number of repos to seed/boot (default 50)",
    )
    parser.addoption(
        "--keep-stack",
        action="store_true",
        default=False,
        help="do not tear the compose stack down after the run",
    )


@pytest.fixture(scope="session")
def repo_count(request) -> int:
    return int(request.config.getoption("--boot-scopes"))


@pytest.fixture(scope="session")
def stack(request, repo_count):
    # Defense-in-depth: this docker-compose suite is already excluded from the
    # repo's default `pytest` run via `testpaths = packages` in pytest.ini, so
    # the unit-test CI matrix never collects it. If it is ever collected in an
    # environment without docker, skip cleanly instead of erroring.
    if shutil.which("docker") is None:
        pytest.skip("docker (compose) is required for the git-leak test bed")
    os.environ["REPO_COUNT"] = str(repo_count)
    # build + start infra; seed runs to completion then exits
    compose("up", "-d", "--build")
    # block until seeding sidecar has finished creating repos. compose() raises
    # (with output) if the seed container exited non-zero, so a hard seed
    # failure surfaces here rather than as a confusing later test failure.
    compose("wait", "seed")
    # Verify the seed actually produced all N repos before any test runs: a
    # partial seed would otherwise look like a server bug when the load gate
    # can't reach N. Fail loudly with the gap.
    # include the reserved probe repo the resilience test relies on, so a
    # partial seed of it is caught here too rather than as a later test failure
    expected = set(list_seeded_repos(repo_count)) | {HEALTHY_PROBE_REPO}
    present = set(GiteaAdmin().list_repos())
    missing = expected - present
    assert not missing, (
        f"seed incomplete: {len(missing)}/{repo_count} repos missing "
        f"(e.g. {sorted(missing)[:5]})"
    )
    client = OpalServerClient()
    client.wait_healthy()
    yield client
    if not request.config.getoption("--keep-stack"):
        compose("down", "-v")


@pytest.fixture()
def opal(stack) -> OpalServerClient:
    # The compose stack is session-scoped (one server for the whole run), but
    # scopes must not leak between tests: clone paths are keyed by repo URL, so
    # a scope left behind by one test shares a cache entry with any later test
    # using the same seeded repo and would pollute its drain assertions.
    #
    # Delete every scope the *server* currently knows (not just this client's
    # tracked set) at setup, so a scope orphaned by a prior failed test can't
    # contaminate this one; then again on teardown.
    stack.delete_all_scopes()
    yield stack
    stack.delete_all_scopes()


@pytest.fixture()
def opal_multiworker(stack) -> OpalServerClient:
    """opal_server reconfigured to 2 gunicorn workers, for the broadcaster
    test.

    The session stack is single-worker (the right call for the per-
    process cache drain assertions), but the Postgres broadcaster's
    cross-worker fan-out — the reason it is in this compose file at all
    — is only exercised with >=2 workers (references/debug-pubsub.md
    §3-4). This force-recreates opal_server with 2 workers for one test,
    then restores the single-worker stack on teardown so the cache tests
    keep their determinism. Each side starts from a clean slate: the
    recreate wipes the container's on-disk clones, and clearing scopes
    stops a leftover scope (whose clone is URL-keyed) from being re-
    cloned on boot.
    """
    os.environ["OPAL_TEST_WORKERS"] = "2"
    try:
        # --no-deps: don't bounce redis/postgres/gitea; --force-recreate: apply
        # the new worker count. No --wait (opal_server has no compose
        # healthcheck) — wait_healthy() polls the HTTP surface instead.
        compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
        stack.wait_healthy()
        stack.delete_all_scopes()
        yield stack
    finally:
        os.environ["OPAL_TEST_WORKERS"] = "1"
        compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
        stack.wait_healthy()
        stack.delete_all_scopes()


@pytest.fixture(scope="session")
def gitea_admin(stack) -> GiteaAdmin:
    """Host-side Gitea admin client (depends on `stack` so Gitea is up)."""
    return GiteaAdmin()
