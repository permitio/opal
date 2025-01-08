import debugpy
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

import docker
from tests.containers.opal_test_container import OpalTestContainer


class PulsarBroadcastContainer(OpalTestContainer, DockerContainer):
    def __init__(
        self,
        network: Network,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        # Add custom labels to the kwargs
        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        self.network = network

        OpalTestContainer.__init__(self)
        DockerContainer.__init__(
            self, image="pulsar:latest", docker_client_kw=docker_client_kw, **kwargs
        )

        self.with_network(self.network)

        self.with_network_aliases("broadcast_channel")
        # Add a custom name for the container
        self.with_name(f"pytest_opal_broadcast_channel")
