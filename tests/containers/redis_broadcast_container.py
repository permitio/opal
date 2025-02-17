from testcontainers.core.network import Network
from testcontainers.redis import RedisContainer

from tests.containers.opal_test_container import OpalTestContainer


class RedisBroadcastContainer(OpalTestContainer, RedisContainer):
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
        RedisContainer.__init__(self, docker_client_kw=docker_client_kw, **kwargs)

        self.with_network(self.network)

        self.with_network_aliases("broadcast_channel")
        # Add a custom name for the container
        self.with_name(f"redis_broadcast_channel")
