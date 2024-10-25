from testcontainers.core.generic import DockerContainer

from . import settings as s


class OpalServerContainer(DockerContainer):
    def __init__(
        self,
        image: str = f"permitio/opal-server:{s.OPAL_IMAGE_TAG}",
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        kwargs.update({"tty": s.OPAL_TESTS_DEBUG})
        super().__init__(image, docker_client_kw, **kwargs)

        self.with_name(s.OPAL_TESTS_SERVER_CONTAINER_NAME)
        self.with_exposed_ports(7002)

        if s.OPAL_TESTS_DEBUG:
            self.with_env("LOG_DIAGNOSE", "true")

        self.with_env("UVICORN_NUM_WORKERS", s.UVICORN_NUM_WORKERS)

        self.with_env("OPAL_POLICY_REPO_URL", s.OPAL_POLICY_REPO_URL)
        self.with_env(
            "OPAL_POLICY_REPO_POLLING_INTERVAL", s.OPAL_POLICY_REPO_POLLING_INTERVAL
        )
        self.with_env("OPAL_POLICY_REPO_MAIN_BRANCH", s.OPAL_POLICY_REPO_MAIN_BRANCH)
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
        # FIXME: The env below is triggerring: did not find main branch: main,...
        # self.with_env("OPAL_STATISTICS_ENABLED", s.OPAL_STATISTICS_ENABLED)


class OpalClientContainer(DockerContainer):
    def __init__(
        self,
        image: str = f"permitio/opal-client:{s.OPAL_IMAGE_TAG}",
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        kwargs.update({"tty": s.OPAL_TESTS_DEBUG})
        super().__init__(image, docker_client_kw, **kwargs)

        self.with_name(s.OPAL_TESTS_CLIENT_CONTAINER_NAME)
        self.with_exposed_ports(7000, 8181)
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
        self.with_env("OPAL_AUTH_JWT_AUDIENCE", s.OPAL_AUTH_JWT_AUDIENCE)
        self.with_env("OPAL_AUTH_JWT_ISSUER", s.OPAL_AUTH_JWT_ISSUER)
        # self.with_env("OPAL_STATISTICS_ENABLED", s.OPAL_STATISTICS_ENABLED)
