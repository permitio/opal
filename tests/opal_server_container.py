from testcontainers.core.generic import DockerContainer
import docker

from . import settings as s

class OpalServerContainer(DockerContainer):
    def __init__(
        self,
        #image: str = f"permitio/opal-server:{s.OPAL_IMAGE_TAG}",
        #image: str = f"opal_server_debug",
        image: str = f"opal_server_debug_local",
        opal_broadcast_uri: str = None,
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        
        super().__init__(image=image, docker_client_kw=docker_client_kw, **kwargs)

        #opal_broadcast_uri = broadcast_channel.get_connection_url(
        #    host=f"{broadcast_channel._name}.{opal_network}", driver=None
        #)
        if not opal_broadcast_uri:
            raise ValueError("Missing 'opal_broadcast_uri'")
        
        self.with_env("OPAL_BROADCAST_URI", opal_broadcast_uri)

        client = docker.from_env()
        
        network = client.networks.get(kwargs.get("network") or s.OPAL_TESTS_NETWORK_NAME)
        self.with_network(network)
    
        self.with_name(s.OPAL_TESTS_SERVER_CONTAINER_NAME)
        self.with_exposed_ports(7002)
        self.with_bind_ports(5678, 5688)

        if s.OPAL_TESTS_DEBUG:
            self.with_env("LOG_DIAGNOSE", "true")
            self.with_env("OPAL_LOG_LEVEL", "DEBUG")

        self.with_env("UVICORN_NUM_WORKERS", s.UVICORN_NUM_WORKERS)

        print("OPAL_POLICY_REPO_URL", s.OPAL_POLICY_REPO_URL)
        self.with_env("OPAL_POLICY_REPO_URL", s.OPAL_POLICY_REPO_URL)
        
        print("OPAL_POLICY_REPO_MAIN_BRANCH", s.OPAL_POLICY_REPO_MAIN_BRANCH)   
        self.with_env("OPAL_POLICY_REPO_MAIN_BRANCH", s.OPAL_POLICY_REPO_MAIN_BRANCH)
        
        self.with_env(
            "OPAL_POLICY_REPO_POLLING_INTERVAL", s.OPAL_POLICY_REPO_POLLING_INTERVAL
        )
        
        if s.OPAL_POLICY_REPO_SSH_KEY:
            self.with_env("OPAL_POLICY_REPO_SSH_KEY", s.OPAL_POLICY_REPO_SSH_KEY)
        self.with_env(
            "OPAL_POLICY_REPO_WEBHOOK_SECRET", s.OPAL_POLICY_REPO_WEBHOOK_SECRET
        )
        self.with_env(
            "OPAL_POLICY_REPO_WEBHOOK_PARAMS", s.OPAL_POLICY_REPO_WEBHOOK_PARAMS
        )

        self.with_env("OPAL_DATA_CONFIG_SOURCES", s.OPAL_DATA_CONFIG_SOURCES)
        self.with_env("OPAL_LOG_FORMAT_INCLUDE_PID", s.OPAL_LOG_FORMAT_INCLUDE_PID)

        self.with_env("OPAL_AUTH_MASTER_TOKEN", s.OPAL_AUTH_MASTER_TOKEN)

        self.with_env("OPAL_AUTH_PUBLIC_KEY", s.OPAL_AUTH_PUBLIC_KEY)
        self.with_env("OPAL_AUTH_PRIVATE_KEY", s.OPAL_AUTH_PRIVATE_KEY)
        if s.OPAL_AUTH_PRIVATE_KEY_PASSPHRASE:
            self.with_env(
                "OPAL_AUTH_PRIVATE_KEY_PASSPHRASE", s.OPAL_AUTH_PRIVATE_KEY_PASSPHRASE
            )
        self.with_env("OPAL_AUTH_JWT_AUDIENCE", s.OPAL_AUTH_JWT_AUDIENCE)
        self.with_env("OPAL_AUTH_JWT_ISSUER", s.OPAL_AUTH_JWT_ISSUER)
        self.with_kwargs(labels={"com.docker.compose.project": "pytest"})

        # FIXME: The env below is triggerring: did not find main branch: main,...
        # self.with_env("OPAL_STATISTICS_ENABLED", s.OPAL_STATISTICS_ENABLED)

