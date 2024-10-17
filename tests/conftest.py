from secrets import token_hex
import time
import pytest
from testcontainers.core.generic import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

from tests.containers import OpalClientContainer, OpalServerContainer

# https://stackoverflow.com/questions/7119452/git-commit-from-python


@pytest.fixture(scope="session")
def broadcast_channel():
    with PostgresContainer("postgres:alpine", driver=None).with_name(
        f"pytest_{token_hex(2)}_broadcast_channel"
    ) as container:
        yield container


@pytest.fixture(scope="session")
def opal_server(broadcast_channel: PostgresContainer):
    opal_broadcast_uri = broadcast_channel.get_connection_url()

    with OpalServerContainer("permitio/opal-server").with_env(
        "OPAL_BROADCAST_URI", opal_broadcast_uri
    ) as container:
        wait_for_logs(container, "Clone succeeded")
        yield container


@pytest.fixture(scope="session", autouse=True)
def opal_client(opal_server: OpalServerContainer):
    opal_server_url = (
        f"http://{get_container_ip(opal_server)}:{opal_server.get_exposed_port(7002)}"
    )

    with OpalClientContainer().with_env(
        "OPAL_SERVER_URL", opal_server_url
    ) as container:
        wait_for_logs(container, "")
        yield container
        time.sleep(300)


def get_container_ip(container: DockerContainer):
    _container = container.get_wrapped_container()
    _container.reload()
    return _container.attrs.get("NetworkSettings", {}).get("IPAddress")
