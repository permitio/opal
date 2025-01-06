import os

import pytest
from testcontainers.core.network import Network
from testcontainers.core.utils import setup_logger

from tests.containers.gitea_container import GiteaContainer
from tests.containers.settings.gitea_settings import GiteaSettings
from tests.policy_repos.policy_repo_base import PolicyRepoBase
from tests.policy_repos.policy_repo_factory import (
    PolicyRepoFactory,
    SupportedPolicyRepo,
)
from tests.policy_repos.policy_repo_settings import PolicyRepoSettings
from tests.settings import pytest_settings

logger = setup_logger(__name__)


@pytest.fixture(scope="session")
def gitea_settings():
    """Returns a GiteaSettings object with default values for the Gitea
    container name, repository name, temporary directory, and data directory.

    This fixture is used to create a Gitea container for testing and to
    initialize the repository settings for the policy repository.

    :return: A GiteaSettings object with default settings.
    """
    return GiteaSettings(
        container_name="gitea_server",
        repo_name="test_repo",
        temp_dir=os.path.join(os.path.dirname(__file__), "temp"),
        data_dir=os.path.join(os.path.dirname(__file__), "../policies"),
    )


@pytest.fixture(scope="session")
def gitea_server(opal_network: Network, gitea_settings: GiteaSettings):
    """Creates a Gitea container and initializes a test repository.

    The Gitea container is created with the default settings for the
    container name, repository name, temporary directory, and data
    directory. The container is then started and the test repository is
    initialized.

    The fixture yields the GiteaContainer object, which can be used to
    interact with the Gitea container.

    :param opal_network: The network to create the container on.
    :param gitea_settings: The settings for the Gitea container.
    :return: The GiteaContainer object.
    """
    with GiteaContainer(
        settings=gitea_settings,
        network=opal_network,
    ) as gitea_container:
        gitea_container.deploy_gitea()
        gitea_container.init_repo()
        yield gitea_container


@pytest.fixture(scope="session")
def policy_repo(
    gitea_settings: GiteaSettings, temp_dir: str, request
) -> PolicyRepoBase:
    """Creates a policy repository for testing.

    This fixture creates a policy repository based on the configuration
    specified in pytest.ini. The repository is created with the default
    branch name "master" and is initialized with the policies from the
    source repository specified in pytest.ini.

    The fixture yields the PolicyRepoBase object, which can be used to
    interact with the policy repository.

    :param gitea_settings: The settings for the Gitea container.
    :param temp_dir: The temporary directory to use for the policy
        repository.
    :param request: The pytest request object.
    :return: The PolicyRepoBase object.
    """
    if pytest_settings.policy_repo_provider == SupportedPolicyRepo.GITEA:
        gitea_server = request.getfixturevalue("gitea_server")

    repo_settings = PolicyRepoSettings(
        temp_dir,
        pytest_settings.repo_owner,
        pytest_settings.repo_name,
        "master",
        gitea_settings.container_name,
        gitea_settings.port_http,
        gitea_settings.port_ssh,
        pytest_settings.repo_password,
        None,
        pytest_settings.ssh_key_path,
        pytest_settings.source_repo_owner,
        pytest_settings.source_repo_name,
        True,
        True,
        pytest_settings.webhook_secret,
    )
    policy_repo = PolicyRepoFactory(
        pytest_settings.policy_repo_provider
    ).get_policy_repo(
        repo_settings,
        logger,
    )

    policy_repo.setup(gitea_settings)
    return policy_repo
