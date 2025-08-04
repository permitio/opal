import time
import docker
import pytest
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

from tests.containers import OpalClientContainer, OpalServerContainer

from . import settings as s


@pytest.fixture(scope="session")
def opal_network():
    client = docker.from_env()
    network = client.networks.create(s.OPAL_TESTS_NETWORK_NAME, driver="bridge")
    yield network.name
    network.remove()


@pytest.fixture(scope="session")
def broadcast_channel(opal_network: str):
    with PostgresContainer("postgres:alpine", network=opal_network).with_name(
        f"pytest_opal_brodcast_channel_{s.OPAL_TESTS_UNIQ_ID}"
    ) as container:
        yield container


@pytest.fixture(scope="session")
def opal_server(opal_network: str, broadcast_channel: PostgresContainer):
    opal_broadcast_uri = broadcast_channel.get_connection_url(
        host=f"{broadcast_channel._name}.{opal_network}", driver=None
    )

    with OpalServerContainer(network=opal_network).with_env(
        "OPAL_BROADCAST_URI", opal_broadcast_uri
    ) as container:
        container.get_wrapped_container().reload()
        print(container.get_wrapped_container().id)
        wait_for_logs(container, "Clone succeeded")
        yield container


@pytest.fixture(scope="session")
def opal_client(opal_network: str, opal_server: OpalServerContainer):
    opal_server_url = f"http://{opal_server._name}.{opal_network}:7002"

    with OpalClientContainer(network=opal_network).with_env(
        "OPAL_SERVER_URL", opal_server_url
    ) as container:
        wait_for_logs(container, "")
        yield container


@pytest.fixture(scope="session", autouse=True)
def setup(opal_server, opal_client):
    yield
    if s.OPAL_TESTS_DEBUG:
        s.dump_settings()
        time.sleep(3600)  # Giving us some time to inspect the containers