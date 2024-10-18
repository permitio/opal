import time
from secrets import token_hex

import docker
import pytest
from testcontainers.core.generic import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

from tests.containers import OpalClientContainer, OpalServerContainer

# https://stackoverflow.com/questions/7119452/git-commit-from-python


@pytest.fixture(scope="session")
def opal_network():
    client = docker.from_env()
    network = client.networks.create(f"pytest_opal_{token_hex(2)}", driver="bridge")
    yield network.name
    network.remove()


@pytest.fixture(scope="session")
def broadcast_channel(opal_network: str):
    with PostgresContainer(
        "postgres:alpine", driver=None, network=opal_network
    ).with_name(f"pytest_{token_hex(2)}_broadcast_channel") as container:
        # opal_network.connect(container.get_wrapped_container())
        yield container


@pytest.fixture(scope="session")
def opal_server(opal_network: str, broadcast_channel: PostgresContainer):
    opal_broadcast_uri = broadcast_channel.get_connection_url()

    with OpalServerContainer(network=opal_network).with_env(
        "OPAL_BROADCAST_URI", opal_broadcast_uri
    ) as container:
        # opal_network.connect(container.get_wrapped_container())
        wait_for_logs(container, "Clone succeeded")
        yield container


@pytest.fixture(scope="session", autouse=True)
def opal_client(opal_network: str, opal_server: OpalServerContainer):
    opal_server_url = f"http://{opal_server._name}.{opal_network}:7002"
    print(f"{opal_server_url=}")

    with OpalClientContainer(network=opal_network).with_env(
        "OPAL_SERVER_URL", opal_server_url
    ) as container:
        wait_for_logs(container, "")
        yield container
        time.sleep(300)


def get_container_ip(container: DockerContainer):
    _container = container.get_wrapped_container()
    _container.reload()
    return _container.attrs.get("NetworkSettings", {}).get("IPAddress")
