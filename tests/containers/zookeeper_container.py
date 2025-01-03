import debugpy
from containers.permitContainer import PermitContainer
from testcontainers.core import DockerContainer
from testcontainers.core.network import Network

import docker


class ZookeeperContainer(PermitContainer, DockerContainer):
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

        PermitContainer.__init__(self)
        DockerContainer.__init__(self, docker_client_kw=docker_client_kw, **kwargs)

        self.with_network(self.network)

        self.with_network_aliases("zookeper")
        # Add a custom name for the container
        self.with_name(f"zookeeper")
