import pytest
from testcontainers.core.network import Network

from tests.containers.kafka_broadcast_container import KafkaBroadcastContainer
from tests.containers.kafka_ui_container import KafkaUIContainer
from tests.containers.postgres_broadcast_container import PostgresBroadcastContainer
from tests.containers.redis_broadcast_container import RedisBroadcastContainer
from tests.containers.redis_ui_container import RedisUIContainer
from tests.containers.settings.postgres_broadcast_settings import (
    PostgresBroadcastSettings,
)
from tests.containers.zookeeper_container import ZookeeperContainer


@pytest.fixture(scope="session")
def postgres_broadcast_channel(opal_network: Network):
    with PostgresBroadcastContainer(
        network=opal_network, settings=PostgresBroadcastSettings()
    ) as container:
        yield container


@pytest.fixture(scope="session")
def kafka_broadcast_channel(opal_network: Network):
    with ZookeeperContainer(opal_network) as zookeeper_container:
        with KafkaBroadcastContainer(
            opal_network, zookeeper_container
        ) as kafka_container:
            with KafkaUIContainer(opal_network, kafka_container) as kafka_ui_container:
                containers = [zookeeper_container, kafka_container, kafka_ui_container]
                yield containers

                for container in containers:
                    container.stop()


@pytest.fixture(scope="session")
def redis_broadcast_channel(opal_network: Network):
    with RedisBroadcastContainer(opal_network) as redis_container:
        with RedisUIContainer(opal_network, redis_container) as redis_ui_container:
            containers = [redis_container, redis_ui_container]
            yield containers

            for container in containers:
                container.stop()


@pytest.fixture(scope="session")
def broadcast_channel(opal_network: Network, postgres_broadcast_channel):
    yield postgres_broadcast_channel
