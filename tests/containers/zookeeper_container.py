import debugpy
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

import docker
from tests.containers.permitContainer import PermitContainer


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
        DockerContainer.__init__(
            self,
            image="confluentinc/cp-zookeeper:latest",
            docker_client_kw=docker_client_kw,
            **kwargs,
        )

        self.with_bind_ports(2181, 2181)
        self.with_env("ZOOKEEPER_CLIENT_PORT", "2181")
        self.with_env("ZOOKEEPER_TICK_TIME", "2000")
        self.with_env("ALLOW_ANONYMOUS_LOGIN", "yes")

        self.with_network(self.network)

        self.with_network_aliases("zookeper")
        # Add a custom name for the container
        self.with_name(f"zookeeper")
