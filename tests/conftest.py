import json
import pytest

from tests.containers import OpalServerContainer
from .settings import *  # noqa: F403
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.core.generic import DockerContainer
from testcontainers.postgres import PostgresContainer

# https://stackoverflow.com/questions/7119452/git-commit-from-python


@pytest.fixture
def broadcast_channel():
    with PostgresContainer("postgres:14.1-alpine", driver=None) as postgres:
        yield postgres


@pytest.fixture(autouse=True)
def opal_server(broadcast_channel: PostgresContainer):
    OPAL_BROADCAST_URI = broadcast_channel.get_connection_url()
    container = OpalServerContainer("permitio/opal-server").with_env(
        "OPAL_BROADCAST_URI", OPAL_BROADCAST_URI
    )
    container.start()
    print(container.env)
    wait_for_logs(container, "Clone succeeded")
    print("port:", container.get_container_host_ip(), container.get_exposed_port(7002))
    yield
    container.stop()


@pytest.fixture
def opal_client(): ...
