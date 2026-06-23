import os
import shutil

import pytest
from helpers import GiteaAdmin, OpalServerClient, compose


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
    # block until seeding sidecar has finished creating repos
    compose("wait", "seed")
    client = OpalServerClient()
    client.wait_healthy()
    yield client
    if not request.config.getoption("--keep-stack"):
        compose("down", "-v")


@pytest.fixture()
def opal(stack) -> OpalServerClient:
    return stack


@pytest.fixture(scope="session")
def gitea_admin(stack) -> GiteaAdmin:
    """Host-side Gitea admin client (depends on `stack` so Gitea is up)."""
    return GiteaAdmin()
