import json
from . import settings as s
from testcontainers.core.generic import DockerContainer


class OpalServerContainer(DockerContainer):
    def __init__(
        self,
        image: str = "permitio/opal-server:latest",
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(image, docker_client_kw, **kwargs)

        self.with_bind_ports(7002, 7002)
        self.with_env("UVICORN_NUM_WORKERS", s.UVICORN_NUM_WORKERS)
        self.with_env("OPAL_POLICY_REPO_URL", s.OPAL_POLICY_REPO_URL)
        self.with_env("OPAL_POLICY_REPO_SSH_KEY", s.OPAL_POLICY_REPO_SSH_KEY)
        self.with_env("OPAL_POLICY_REPO_MAIN_BRANCH", s.OPAL_POLICY_REPO_MAIN_BRANCH)
        self.with_env(
            "OPAL_POLICY_REPO_POLLING_INTERVAL", s.OPAL_POLICY_REPO_POLLING_INTERVAL
        )
        self.with_env("PAL_DATA_CONFIG_SOURCES", json.dumps(s.OPAL_DATA_CONFIG_SOURCES))
        self.with_env("OPAL_LOG_FORMAT_INCLUDE_PID", s.OPAL_LOG_FORMAT_INCLUDE_PID)
        self.with_env(
            "OPAL_POLICY_REPO_WEBHOOK_SECRET", s.OPAL_POLICY_REPO_WEBHOOK_SECRET
        )
        self.with_env(
            "OPAL_POLICY_REPO_WEBHOOK_PARAMS", s.OPAL_POLICY_REPO_WEBHOOK_PARAMS
        )
        self.with_env("OPAL_AUTH_PUBLIC_KEY", s.OPAL_AUTH_PUBLIC_KEY)
        self.with_env("OPAL_AUTH_PRIVATE_KEY", s.OPAL_AUTH_PRIVATE_KEY)
        self.with_env("OPAL_AUTH_MASTER_TOKEN", s.OPAL_AUTH_MASTER_TOKEN)
        self.with_env("OPAL_AUTH_JWT_AUDIENCE", s.OPAL_AUTH_JWT_AUDIENCE)
        self.with_env("OPAL_AUTH_JWT_ISSUER", s.OPAL_AUTH_JWT_ISSUER)
        # FIXME: The env below is triggerring: did not find main branch: main,...
        # self.with_env("OPAL_STATISTICS_ENABLED", s.OPAL_STATISTICS_ENABLED)


class OpalClientContainer(DockerContainer): ...
