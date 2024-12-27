import debugpy
import docker
from testcontainers.postgres import PostgresContainer
from testcontainers.core.network import Network


class BroadcastContainer(PostgresContainer):
    def __init__(
        self,
        network: Network,
        image: str = "postgres:alpine",
        name: str = "broadcast_channel",
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        
        self.name = name
        # Add custom labels to the kwargs
        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        self.network = network

        super().__init__(image=image, docker_client_kw=docker_client_kw, **kwargs)

        self.with_network(self.network)

        self.with_network_aliases("broadcast_channel")
        # Add a custom name for the container
        self.with_name(f"pytest_opal_broadcast_channel_{self.name}")