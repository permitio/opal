from testcontainers.core.generic import DockerContainer
import docker

from . import settings as s

class OpalClientContainer(DockerContainer):
    def __init__(
        self,
        #image: str = f"permitio/opal-client:{s.OPAL_IMAGE_TAG}",
        #image: str = f"opal_client_debug",
        image: str = f"opal_client_debug_local",
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(image=image, docker_client_kw=docker_client_kw, **kwargs)

         #opal_server_url = f"http://{opal_server._name}.{opal_network}:7002"
        opal_server_url = f"http://opal_server:7002"
        self.with_env("OPAL_SERVER_URL", opal_server_url)

        client = docker.from_env()
        network = client.networks.get(kwargs.get("network") or s.OPAL_TESTS_NETWORK_NAME)
        self.with_network(network)
    

        self.with_name(s.OPAL_TESTS_CLIENT_CONTAINER_NAME)
        self.with_exposed_ports(7000, 8181)
        self.with_bind_ports(5678, 5698)

        if s.OPAL_TESTS_DEBUG:
            self.with_env("LOG_DIAGNOSE", "true")
            self.with_env("OPAL_LOG_LEVEL", "DEBUG")

        self.with_env("OPAL_LOG_FORMAT_INCLUDE_PID", s.OPAL_LOG_FORMAT_INCLUDE_PID)
        self.with_env("OPAL_INLINE_OPA_LOG_FORMAT", s.OPAL_INLINE_OPA_LOG_FORMAT)
        self.with_env(
            "OPAL_SHOULD_REPORT_ON_DATA_UPDATES", s.OPAL_SHOULD_REPORT_ON_DATA_UPDATES
        )
        self.with_env("OPAL_DEFAULT_UPDATE_CALLBACKS", s.OPAL_DEFAULT_UPDATE_CALLBACKS)
        self.with_env(
            "OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED",
            s.OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED,
        )
        self.with_env("OPAL_CLIENT_TOKEN", s.OPAL_CLIENT_TOKEN)
        self.with_env("OPAL_AUTH_PUBLIC_KEY", s.OPAL_AUTH_PUBLIC_KEY)
        self.with_env("OPAL_AUTH_JWT_AUDIENCE", s.OPAL_AUTH_JWT_AUDIENCE)
        self.with_env("OPAL_AUTH_JWT_ISSUER", s.OPAL_AUTH_JWT_ISSUER)

        self.with_kwargs(labels={"com.docker.compose.project": "pytest"})

        # self.with_env("OPAL_STATISTICS_ENABLED", s.OPAL_STATISTICS_ENABLED)
