import json
import os
import shutil
import tempfile
import threading
import time
from typing import List

import debugpy
import pytest
from testcontainers.core.network import Network
from testcontainers.core.utils import setup_logger
from testcontainers.core.waiting_utils import wait_for_logs

import docker
from tests import utils
from tests.containers.broadcast_container_base import BroadcastContainerBase
from tests.containers.gitea_container import GiteaContainer
from tests.containers.kafka_broadcast_container import KafkaBroadcastContainer
from tests.containers.opal_client_container import OpalClientContainer
from tests.containers.opal_server_container import OpalServerContainer
from tests.containers.postgres_broadcast_container import PostgresBroadcastContainer
from tests.containers.redis_broadcast_container import RedisBroadcastContainer
from tests.containers.settings.gitea_settings import GiteaSettings
from tests.containers.settings.opal_client_settings import OpalClientSettings
from tests.containers.settings.opal_server_settings import OpalServerSettings
from tests.containers.settings.postgres_broadcast_settings import (
    PostgresBroadcastSettings,
)
from tests.policy_repos.policy_repo_base import PolicyRepoBase
from tests.policy_repos.policy_repo_factory import (
    PolicyRepoFactory,
    SupportedPolicyRepo,
)
from tests.settings import TestSettings

logger = setup_logger(__name__)

pytest_settings = TestSettings()

# wait some seconds for the debugger to attach
debugger_wait_time = 5  # seconds


def cancel_wait_for_client_after_timeout():
    time.sleep(debugger_wait_time)
    debugpy.wait_for_client.cancel()


t = threading.Thread(target=cancel_wait_for_client_after_timeout)
t.start()
print(f"Waiting for debugger to attach... {debugger_wait_time} seconds timeout")
debugpy.wait_for_client()

utils.export_env("OPAL_TESTS_DEBUG", "true")
utils.install_opal_server_and_client()


@pytest.fixture(scope="session")
def temp_dir():
    # Setup: Create a temporary directory
    dir_path = tempfile.mkdtemp()
    print(f"Temporary directory created: {dir_path}")
    yield dir_path

    # Teardown: Clean up the temporary directory
    shutil.rmtree(dir_path)
    print(f"Temporary directory removed: {dir_path}")


@pytest.fixture(scope="session")
def build_docker_server_image():
    docker_client = docker.from_env()
    image_name = "opal_server_debug_local"

    yield utils.build_docker_image("Dockerfile.server.local", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")


@pytest.fixture(scope="session")
def build_docker_opa_image():
    docker_client = docker.from_env()
    image_name = "opa"

    yield utils.build_docker_image("Dockerfile.opa", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")


@pytest.fixture(scope="session")
def build_docker_cedar_image():
    docker_client = docker.from_env()
    image_name = "cedar"

    yield utils.build_docker_image("Dockerfile.cedar", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")


@pytest.fixture(scope="session")
def build_docker_client_image():
    docker_client = docker.from_env()
    image_name = "opal_client_debug_local"

    yield utils.build_docker_image("Dockerfile.client.local", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")


@pytest.fixture(scope="session")
def opal_network():
    network = Network().create()

    yield network

    print("Removing network...")
    time.sleep(5)  # wait for the containers to stop
    network.remove()
    print("Network removed")


@pytest.fixture(scope="session")
def gitea_settings():
    return GiteaSettings(
        container_name="gitea_server",
        repo_name="test_repo",
        temp_dir=os.path.join(os.path.dirname(__file__), "temp"),
        data_dir=os.path.join(os.path.dirname(__file__), "policies"),
    )


@pytest.fixture(scope="session")
def gitea_server(opal_network: Network, gitea_settings: GiteaSettings):
    with GiteaContainer(
        settings=gitea_settings,
        network=opal_network,
    ) as gitea_container:
        gitea_container.deploy_gitea()
        gitea_container.init_repo()
        yield gitea_container


@pytest.fixture(scope="session")
def policy_repo(gitea_settings: GiteaSettings, request) -> PolicyRepoBase:
    if pytest_settings.policy_repo_provider == SupportedPolicyRepo.GITEA:
        gitea_server = request.getfixturevalue("gitea_server")

    policy_repo = PolicyRepoFactory(
        pytest_settings.policy_repo_provider
    ).get_policy_repo(temp_dir)
    policy_repo.setup(gitea_settings)
    return policy_repo


@pytest.fixture(scope="session")
def broadcast_channel(opal_network: Network):
    with PostgresBroadcastContainer(
        network=opal_network, settings=PostgresBroadcastSettings()
    ) as container:
        yield container


@pytest.fixture(scope="session")
def kafka_broadcast_channel(opal_network: Network):
    with KafkaBroadcastContainer(opal_network) as container:
        yield container


@pytest.fixture(scope="session")
def redis_broadcast_channel(opal_network: Network):
    with RedisBroadcastContainer(opal_network) as container:
        yield container


@pytest.fixture(scope="session")
def number_of_opal_servers():
    return 2


@pytest.fixture(scope="session")
def opal_server(
    opal_network: Network,
    broadcast_channel: BroadcastContainerBase,
    policy_repo: PolicyRepoBase,
    number_of_opal_servers: int,
):
    if not broadcast_channel:
        raise ValueError("Missing 'broadcast_channel' container.")

    containers = []  # List to store container instances

    for i in range(number_of_opal_servers):
        container_name = f"opal_server_{i+1}"

        container = OpalServerContainer(
            OpalServerSettings(
                broadcast_uri=broadcast_channel.get_url(),
                container_name=container_name,
                container_index=i + 1,
                uvicorn_workers="4",
                policy_repo_url=policy_repo.get_repo_url(),
                image="permitio/opal-server:latest",
            ),
            network=opal_network,
        )

        container.start()
        container.get_wrapped_container().reload()
        print(
            f"Started container: {container_name}, ID: {container.get_wrapped_container().id}"
        )
        container.wait_for_log("Clone succeeded", timeout=30)
        containers.append(container)

    yield containers

    for container in containers:
        container.stop()


@pytest.fixture(scope="session")
def number_of_opal_clients():
    return 2


@pytest.fixture(scope="session")
def connected_clients(opal_client: List[OpalClientContainer]):
    for client in opal_client:
        assert client.wait_for_log(
            log_str="Connected to PubSub server", timeout=30
        ), f"Client {client.settings.container_name} did not connect to PubSub server."
    yield opal_client


@pytest.fixture(scope="session")
def opal_client(
    opal_network: Network,
    opal_server: List[OpalServerContainer],
    request,
    number_of_opal_clients: int,
):
    if not opal_server or len(opal_server) == 0:
        raise ValueError("Missing 'opal_server' container.")

    opal_server_url = f"http://{opal_server[0].settings.container_name}:{opal_server[0].settings.port}"
    client_token = opal_server[0].obtain_OPAL_tokens()["client"]
    callbacks = json.dumps(
        {
            "callbacks": [
                [
                    f"{opal_server_url}/data/callback_report",
                    {
                        "method": "post",
                        "process_data": False,
                        "headers": {
                            "Authorization": f"Bearer {client_token}",
                            "content-type": "application/json",
                        },
                    },
                ]
            ]
        }
    )

    containers = []  # List to store OpalClientContainer instances

    for i in range(number_of_opal_clients):
        container_name = f"opal_client_{i+1}"  # Unique name for each client

        container = OpalClientContainer(
            OpalClientSettings(
                image="permitio/opal-client:latest",
                container_name=container_name,
                container_index=i + 1,
                opal_server_url=opal_server_url,
                client_token=client_token,
                default_update_callbacks=callbacks,
            ),
            network=opal_network,
        )

        container.start()
        print(
            f"Started OpalClientContainer: {container_name}, ID: {container.get_wrapped_container().id}"
        )
        containers.append(container)

    yield containers

    for container in containers:
        container.stop()


@pytest.fixture(scope="session", autouse=True)
def setup(opal_server, opal_client):
    yield

    utils.remove_env("OPAL_TESTS_DEBUG")
    wait_sometime()


def wait_sometime():
    if os.getenv("GITHUB_ACTIONS") == "true":
        print("Running inside GitHub Actions. Sleeping for 30 seconds...")
        time.sleep(3600)  # Sleep for 30 seconds
    else:
        print("Running on the local machine. Press Enter to continue...")
        input()  # Wait for key press
