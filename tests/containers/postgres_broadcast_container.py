from testcontainers.core.network import Network
from testcontainers.postgres import PostgresContainer

from tests.containers.broadcast_container_base import BroadcastContainerBase
from tests.containers.settings.postgres_broadcast_settings import (
    PostgresBroadcastSettings,
)


class PostgresBroadcastContainer(BroadcastContainerBase, PostgresContainer):
    def __init__(
        self,
        network: Network,
        settings: PostgresBroadcastSettings,
        image: str = "postgres:alpine",
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        self.network = network
        self.settings = settings

        BroadcastContainerBase.__init__(self, **kwargs)
        PostgresContainer.__init__(
            self,
            image,
            settings.port,
            settings.user,
            settings.password,
            settings.database,
            docker_client_kw=docker_client_kw,
            **kwargs,
        )

        self.with_network(self.network)

        self.with_network_aliases("broadcast_channel")
        self.with_name(f"postgres_broadcast_channel")

        self.start()
