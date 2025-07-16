from testcontainers.core.generic import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.utils import setup_logger

from tests import utils
from tests.containers.opal_test_container import OpalTestContainer
from tests.containers.settings.opal_client_settings import OpalClientSettings


class OpaSettings:
    def __init__(
        self,
        image: str | None = None,
        port: int | None = None,
        container_name: str | None = None,
    ) -> None:
        self.image = image if image else "openpolicyagent/opa:0.29.0"
        self.container_name = "opa"

        if port is None:
            self.port = utils.find_available_port(8181)
        else:
            if utils.is_port_available(port):
                self.port = port
            else:
                self.port = utils.find_available_port(8181)

    def getEnvVars(self):
        return {}


class OpaContainer(OpalTestContainer, DockerContainer):
    def __init__(
        self,
        settings: OpaSettings,
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
            8181, self.settings.port
        ).with_network(self.network).with_kwargs(
            labels={"com.docker.compose.project": "pytest"}
        ).with_network_aliases(
            self.settings.container_name
        )

    def reload_with_settings(self, settings: OpaSettings | None = None):
        self.stop()

        self.settings = settings if settings else self.settings
        self.configure()

        self.start()
