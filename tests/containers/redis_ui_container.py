from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.redis import RedisContainer

from tests.containers.opal_test_container import OpalTestContainer


class RedisUIContainer(OpalTestContainer, DockerContainer):
    def __init__(
        self,
        network: Network,
        redis_container: RedisContainer,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        # Add custom labels to the kwargs
        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        self.redis_container = redis_container
        self.network = network
        self.container_name = "redis-ui"
        self.image = "redislabs/redisinsight:latest"

        OpalTestContainer.__init__(self)
        DockerContainer.__init__(
            self, image=self.image, docker_client_kw=docker_client_kw, **kwargs
        )

        self.with_name(self.container_name)

        self.with_network(self.network)
        self.with_bind_ports(5540, 5540)

        self.with_network_aliases("redis_ui")
