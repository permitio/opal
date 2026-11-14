"""Fixtures of the E2E suite: one compose stack for the whole run, with its
policy repo on the stack's Gitea, or on github.com over SSH in the GitHub
lane."""

import os
from collections.abc import Iterator

import pytest
from stack import (
    CLIENT_CONNECTED,
    CLIENT_GOT_POLICY,
    CLIENT_LOADED_STATIC_DATA,
    COMPOSE_FILE,
    GITHUB_COMPOSE_FILE,
    REPLICAS,
    Compose,
    Fleet,
    Gitea,
    GitHubPolicyRepo,
    OpalAuth,
    PolicyRepo,
    create_auth,
    new_test_branch,
)

# The scope bed has its own stack, fixtures and pytest.ini.
collect_ignore = ["git-leak"]

DEPLOY_KEY_VARIABLE = "OPAL_TESTS_POLICY_REPO_DEPLOY_KEY"
_COMPOSE_LOGS = pytest.StashKey[str]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--policy-repo",
        choices=("gitea", "github"),
        default="gitea",
        help="where the servers' policy repo is: on the stack's Gitea over HTTP "
        "(default), or on github.com over SSH with the deploy key in "
        f"${DEPLOY_KEY_VARIABLE}",
    )


def pytest_configure(config: pytest.Config) -> None:
    lane = config.getoption("--policy-repo")
    if lane == "github" and not os.environ.get(DEPLOY_KEY_VARIABLE):
        raise pytest.UsageError(
            f"--policy-repo=github pushes to the policy repo on github.com: set "
            f"{DEPLOY_KEY_VARIABLE} to a deploy key with write access"
        )


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    logs = config.stash.get(_COMPOSE_LOGS, None)
    if logs:
        terminalreporter.section("docker compose logs")
        terminalreporter.write(logs)


@pytest.fixture(scope="session")
def lane(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--policy-repo")


@pytest.fixture(scope="session")
def auth(tmp_path_factory: pytest.TempPathFactory) -> OpalAuth:
    tag = os.environ.get("OPAL_IMAGE_TAG") or "latest"
    return create_auth(tmp_path_factory.mktemp("auth"), f"permitio/opal-server:{tag}")


@pytest.fixture(scope="session")
def branch() -> str:
    """The policy repo branch the servers track, new for each run."""
    return new_test_branch()


@pytest.fixture(scope="session")
def compose(
    request: pytest.FixtureRequest, auth: OpalAuth, lane: str, branch: str
) -> Iterator[Compose]:
    """The stack's compose project, down before the run and after it.

    When a test failed, the run ends with the stack's logs.
    """
    files = [COMPOSE_FILE]
    variables = {
        **auth.server_variables(),
        "OPAL_CLIENT_TOKEN": auth.client_token,
        "POLICY_REPO_BRANCH": branch,
    }
    if lane == "github":
        files.append(GITHUB_COMPOSE_FILE)
        deploy_key = os.environ[DEPLOY_KEY_VARIABLE].strip()
        variables["OPAL_POLICY_REPO_SSH_KEY"] = deploy_key.replace("\n", "_")
    compose = Compose(files, variables)
    compose("down", "--volumes", "--remove-orphans")
    yield compose
    if request.session.testsfailed:
        request.config.stash[_COMPOSE_LOGS] = compose("logs", "--no-color")
    compose("down", "--volumes", "--remove-orphans")


@pytest.fixture(scope="session")
def policy_repo(
    compose: Compose,
    lane: str,
    branch: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[PolicyRepo]:
    """A working copy of the policy repo on the branch the servers track."""
    home = tmp_path_factory.mktemp("policy-repo")
    if lane == "github":
        repo = GitHubPolicyRepo.clone(os.environ[DEPLOY_KEY_VARIABLE], home, branch)
        yield repo
        repo.git("push", "--quiet", "origin", "--delete", branch)
        return
    compose("up", "--detach", "--wait", "gitea")
    gitea = Gitea(compose)
    gitea.create_admin()
    yield gitea.create_policy_repo(home, branch)


@pytest.fixture(scope="session")
def fleet(compose: Compose, auth: OpalAuth, policy_repo: PolicyRepo) -> Fleet:
    """The whole stack, up once each client has connected to a server and
    loaded the policy and the static data."""
    compose("up", "--detach", "--wait", "--wait-timeout", "300")
    running = compose("ps", "--status", "running", "--format", "{{.Service}}")
    for service in ("opal_server", "opal_client"):
        assert running.split().count(service) == len(REPLICAS), running
    fleet = Fleet(compose, auth.data_source_token)
    for line in (CLIENT_CONNECTED, CLIENT_GOT_POLICY, CLIENT_LOADED_STATIC_DATA):
        fleet.wait_for_each_client(line, timeout=120)
    return fleet
