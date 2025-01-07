import requests
from testcontainers.core.generic import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.utils import setup_logger

from tests.containers.permitContainer import PermitContainer
from tests.containers.settings.opal_server_settings import OpalServerSettings


class OpalServerContainer(PermitContainer, DockerContainer):
    def __init__(
        self,
        settings: OpalServerSettings,
        network: Network,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        self.settings = settings
        self.network = network

        self.logger = setup_logger(__name__)

        PermitContainer.__init__(self)
        DockerContainer.__init__(
            self, image=self.settings.image, docker_client_kw=docker_client_kw, **kwargs
        )

        self.configure()

    def configure(self):
        # Add environment variables individually
        for key, value in self.settings.getEnvVars().items():
            self.with_env(key, value)

        # Configure network and other settings
        self.with_name(self.settings.container_name).with_bind_ports(
            7002, self.settings.port
        ).with_network(self.network).with_kwargs(
            labels={"com.docker.compose.project": "pytest"}
        ).with_network_aliases(
            self.settings.container_name
        )

        # Bind debug ports if enabled
        if self.settings.debugEnabled:
            self.with_bind_ports(5678, self.settings.debug_port)

    def reload_with_settings(self, settings: OpalServerSettings | None = None):
        self.stop()

        self.settings = settings if settings else self.settings
        self.configure()

        self.start()

    def obtain_OPAL_tokens(self, caller: str = "Unkonwn caller") -> dict:
        """Fetch client and datasource tokens from the OPAL server."""
        token_url = f"http://localhost:{self.settings.port}/token"
        headers = {
            "Authorization": f"Bearer {self.settings.master_token}",
            "Content-Type": "application/json",
        }

        tokens = {}

        for token_type in ["client", "datasource"]:
            try:
                data = {"type": token_type}  # ).replace("'", "\"")
                self.logger.debug(f"Fetching OPAL {token_type} token...")
                self.logger.debug(f"url: {token_url}")
                self.logger.debug(f"headers: {headers}")
                self.logger.debug(data)

                response = requests.post(token_url, headers=headers, json=data)
                response.raise_for_status()

                token = response.json().get("token")
                if token:
                    tokens[token_type] = token
                    self.logger.info(f"{caller} | Successfully fetched OPAL {token_type} token.")
                else:
                    self.logger.error(
                        f"{caller} | Failed to fetch OPAL {token_type} token: {response.json()}"
                    )

            except requests.exceptions.RequestException as e:
                self.logger.error(
                    f"{caller} | HTTP Request failed while fetching OPAL {token_type} token: {e}"
                )

        return tokens
