import debugpy
from testcontainers.core.network import Network
from testcontainers.kafka import KafkaContainer

import docker
from tests.containers.permitContainer import PermitContainer
from tests.containers.zookeeper_container import ZookeeperContainer


class KafkaBroadcastContainer(PermitContainer, KafkaContainer):
    def __init__(
        self,
        network: Network,
        zookeeper_container: ZookeeperContainer,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        # Add custom labels to the kwargs
        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        self.zookeeper_container = zookeeper_container
        self.network = network

        PermitContainer.__init__(self)
        KafkaContainer.__init__(self, docker_client_kw=docker_client_kw, **kwargs)

        self.with_network(self.network)

        self.with_network_aliases("broadcast_channel")
        # Add a custom name for the container
        self.with_name(f"kafka_broadcast_channel")
