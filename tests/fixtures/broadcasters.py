import pytest
from testcontainers.core.network import Network

from tests.containers.kafka_broadcast_container import KafkaBroadcastContainer
from tests.containers.postgres_broadcast_container import PostgresBroadcastContainer
from tests.containers.redis_broadcast_container import RedisBroadcastContainer
from tests.containers.settings.postgres_broadcast_settings import (
    PostgresBroadcastSettings,
)


@pytest.fixture(scope="session")
def postgres_broadcast_channel(opal_network: Network):
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
def broadcast_channel(opal_network: Network, postgres_broadcast_channel):
    yield postgres_broadcast_channel
