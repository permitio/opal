from tests.containers.settings.opal_client_settings import OpalClientSettings
from testcontainers.core.generic import DockerContainer
from testcontainers.core.utils import setup_logger
from testcontainers.core.network import Network
from containers.permitContainer import PermitContainer


class OpalClientContainer(PermitContainer, DockerContainer):
    def __init__(
        self,
        settings: OpalClientSettings,
        network: Network,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        PermitContainer.__init__(self)  # Initialize PermitContainer
        DockerContainer.__init__(self, image=settings.image, docker_client_kw=docker_client_kw, **kwargs)
        self.settings = settings
        self.network = network
        self.logger = setup_logger(__name__)
        self.configure()


    def configure(self):
        for key, value in self.settings.getEnvVars().items():
            self.with_env(key, value)

        # TODO: Ari: we need to handle these lines
         #opal_server_url = f"http://{opal_server._name}.{opal_network}:7002"
        opal_server_url = f"http://opal_server:7002"
        self.with_env("OPAL_SERVER_URL", opal_server_url)

        self.with_network(self.network)
    

        self \
            .with_name(self.settings.container_name) \
            .with_bind_ports(7000, 7000) \
            .with_bind_ports(8181, self.settings.opa_port) \
            .with_network(self.network) \
            .with_network_aliases("opal_client") \
            .with_kwargs(labels={"com.docker.compose.project": "pytest"})

        if self.settings.debug_enabled:
            self.with_bind_ports(5678, 5698)
            
    def reload_with_settings(self, settings: OpalClientSettings | None = None):
        
        self.stop()
        
        self.settings = settings if settings else self.settings
        self.configure()

        self.start()