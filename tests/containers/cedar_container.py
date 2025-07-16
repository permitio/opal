from testcontainers.core.generic import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.utils import setup_logger

from tests import utils
from tests.containers.opal_test_container import OpalTestContainer
from tests.containers.settings.cedar_settings import CedarSettings
from tests.containers.settings.opal_client_settings import OpalClientSettings


class CedarContainer(OpalTestContainer, DockerContainer):
    def __init__(
        self,
        settings: CedarSettings,
        network: Network,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        OpalTestContainer.__init__(self)  # Initialize OpalTestContainer
        DockerContainer.__init__(
            self, image=settings.image, docker_client_kw=docker_client_kw, **kwargs
        )
        self.settings = settings
        self.network = network
        self.logger = setup_logger(__name__)
        self.configure()

    def configure(self):
        for key, value in self.settings.getEnvVars().items():
            self.with_env(key, value)

        self.with_name(self.settings.container_name).with_bind_ports(
            8180, self.settings.port
        ).with_network(self.network).with_kwargs(
            labels={"com.docker.compose.project": "pytest"}
        ).with_network_aliases(
            self.settings.container_name
        )

    def reload_with_settings(self, settings: CedarSettings | None = None):
        self.stop()

        self.settings = settings if settings else self.settings
        self.configure()

        self.start()
