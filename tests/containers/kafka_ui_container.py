from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from tests.containers.kafka_broadcast_container import KafkaBroadcastContainer
from tests.containers.permitContainer import PermitContainer


class KafkaUIContainer(PermitContainer, DockerContainer):
    def __init__(
        self,
        network: Network,
        kafka_container: KafkaBroadcastContainer,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        # Add custom labels to the kwargs
        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        self.kafka_container = kafka_container
        self.network = network

        self.with_name("kafka-ui")
        self.image = "provectuslabs/kafka-ui:latest"

        PermitContainer.__init__(self)
        DockerContainer.__init__(
            self, image=self.image, docker_client_kw=docker_client_kw, **kwargs
        )

        self.with_bind_ports(8080, 8080)
        self.with_env("KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS", "kafka:9092")

        self.with_network(self.network)
        self.with_network_aliases("Kafka_ui")
