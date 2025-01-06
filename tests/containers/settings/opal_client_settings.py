import os

from testcontainers.core.utils import setup_logger

from tests import utils


class OpalClientSettings:
    def __init__(
        self,
        client_token: str | None = None,
        container_name: str | None = None,
        port: int | None = None,
        opal_server_url: str | None = None,
        should_report_on_data_updates: str | None = None,
        log_format_include_pid: str | None = None,
        tests_debug: bool | None = False,
        log_diagnose: str | None = None,
        log_level: str | None = None,
        debug_enabled: bool | None = None,
        debug_port: int | None = None,
        image: str | None = None,
        opa_port: int | None = None,
        default_update_callbacks: str | None = None,
        opa_health_check_policy_enabled: str | None = None,
        auth_jwt_audience: str | None = None,
        auth_jwt_issuer: str | None = None,
        statistics_enabled: str | None = None,
        policy_store_type: str | None = None,
        policy_store_url: str | None = None,
        iniline_cedar_enabled: str | None = None,
        inline_cedar_exec_path: str | None = None,
        inline_cedar_config: str | None = None,
        inline_cedar_log_format: str | None = None,
        inline_opa_enabled: bool | None = None,
        inline_opa_exec_path: str | None = None,
        inline_opa_config: str | None = None,
        inline_opa_log_format: str | None = None,
        uvicorn_asgi_app: str | None = None,
        container_index: int = 1,
        topics: str | None = None,
        **kwargs,
    ):
        self.logger = setup_logger("OpalClientSettings")

        self.load_from_env()

        self.image = image if image else self.image
        self.container_name = container_name if container_name else self.container_name
        self.port = port if port else self.port
        self.opal_server_url = (
            opal_server_url if opal_server_url else self.opal_server_url
        )
        self.opa_port = opa_port if opa_port else self.opa_port
        self.should_report_on_data_updates = (
            should_report_on_data_updates
            if should_report_on_data_updates
            else self.should_report_on_data_updates
        )
        self.log_format_include_pid = (
            log_format_include_pid
            if log_format_include_pid
            else self.log_format_include_pid
        )

        self.tests_debug = tests_debug if tests_debug else self.tests_debug
        self.log_diagnose = log_diagnose if log_diagnose else self.log_diagnose
        self.log_level = log_level if log_level else self.log_level
        self.debug_enabled = debug_enabled if debug_enabled else self.debug_enabled
        self.default_update_callbacks = (
            default_update_callbacks
            if default_update_callbacks
            else self.default_update_callbacks
        )
        self.client_token = client_token if client_token else self.client_token
        self.opa_health_check_policy_enabled = (
            opa_health_check_policy_enabled
            if opa_health_check_policy_enabled
            else self.opa_health_check_policy_enabled
        )
        self.auth_jwt_audience = (
            auth_jwt_audience if auth_jwt_audience else self.auth_jwt_audience
        )
        self.auth_jwt_issuer = (
            auth_jwt_issuer if auth_jwt_issuer else self.auth_jwt_issuer
        )
        self.statistics_enabled = (
            statistics_enabled if statistics_enabled else self.statistics_enabled
        )
        self.container_index = (
            container_index if container_index else self.container_index
        )
        self.debug_port = debug_port if debug_port else self.debug_port
        self.__dict__.update(kwargs)

        self.policy_store_type = (
            policy_store_type if policy_store_type else self.policy_store_type
        )
        self.policy_store_url = (
            policy_store_url if policy_store_url else self.policy_store_url
        )

        self.uvicorn_asgi_app = (
            uvicorn_asgi_app if uvicorn_asgi_app else self.uvicorn_asgi_app
        )

        if self.container_index > 1:
            self.opa_port += self.container_index - 1
            # self.port += self.container_index - 1
            self.debug_port += self.container_index - 1

        self.iniline_cedar_enabled = (
            iniline_cedar_enabled
            if iniline_cedar_enabled
            else self.iniline_cedar_enabled
        )
        self.inline_cedar_exec_path = (
            inline_cedar_exec_path
            if inline_cedar_exec_path
            else self.inline_cedar_exec_path
        )
        self.inline_cedar_config = (
            inline_cedar_config if inline_cedar_config else self.inline_cedar_config
        )
        self.inline_cedar_log_format = (
            inline_cedar_log_format
            if inline_cedar_log_format
            else self.inline_cedar_log_format
        )

        self.inline_opa_enabled = (
            inline_opa_enabled if inline_opa_enabled else self.inline_opa_enabled
        )
        self.inline_opa_exec_path = (
            inline_opa_exec_path if inline_opa_exec_path else self.inline_opa_exec_path
        )
        self.inline_opa_config = (
            inline_opa_config if inline_opa_config else self.inline_opa_config
        )
        self.inline_opa_log_format = (
            inline_opa_log_format
            if inline_opa_log_format
            else self.inline_opa_log_format
        )
        self.topics = topics if topics else self.topics

        self.validate_dependencies()

    def validate_dependencies(self):
        if not self.image:
            raise ValueError("OPAL_CLIENT_IMAGE is required.")
        if not self.container_name:
            raise ValueError("OPAL_CLIENT_CONTAINER_NAME is required.")
        if not self.opal_server_url:
            raise ValueError("OPAL_SERVER_URL is required.")

        self.logger.info(
            f"{self.container_name} | Dependencies validated successfully."
        )

    def getEnvVars(self):
        env_vars = {
            "OPAL_SERVER_URL": self.opal_server_url,
            "OPAL_LOG_FORMAT_INCLUDE_PID": self.log_format_include_pid,
            "OPAL_SHOULD_REPORT_ON_DATA_UPDATES": self.should_report_on_data_updates,
            "OPAL_DEFAULT_UPDATE_CALLBACKS": self.default_update_callbacks,
            "OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED": self.opa_health_check_policy_enabled,
            "OPAL_CLIENT_TOKEN": self.client_token,
            "OPAL_AUTH_JWT_AUDIENCE": self.auth_jwt_audience,
            "OPAL_AUTH_JWT_ISSUER": self.auth_jwt_issuer,
            "OPAL_STATISTICS_ENABLED": self.statistics_enabled,
            # TODO: make not hardcoded
            "OPAL_DATA_TOPICS": self.topics,
            "UVICORN_ASGI_APP": self.uvicorn_asgi_app,
            "UVICORN_NUM_WORKERS": "1",
            "UVICORN_PORT": str(self.port),
        }

        if self.tests_debug:
            env_vars["LOG_DIAGNOSE"] = self.log_diagnose
            env_vars["OPAL_LOG_LEVEL"] = self.log_level

        if self.policy_store_type:
            env_vars["OPAL_POLICY_STORE_TYPE"] = self.policy_store_type

        if self.policy_store_url:
            env_vars["OPAL_POLICY_STORE_URL"] = self.policy_store_url

        if self.inline_opa_enabled:
            env_vars["OPAL_INLINE_OPA_ENABLED"] = self.inline_opa_enabled
            env_vars["OPAL_INLINE_OPA_EXEC_PATH"] = self.inline_opa_exec_path
            env_vars["OPAL_INLINE_OPA_CONFIG"] = self.inline_opa_config
            env_vars["OPAL_INLINE_OPA_LOG_FORMAT"] = self.inline_opa_log_format

        if self.iniline_cedar_enabled:
            env_vars["OPAL_INILINE_CEDAR_ENABLED"] = self.iniline_cedar_enabled
            env_vars["OPAL_INILINE_CEDAR_EXEC_PATH"] = self.inline_cedar_exec_path
            env_vars["OPAL_INILINE_CEDAR_CONFIG"] = self.inline_cedar_config
            env_vars["OPAL_INILINE_CEDAR_LOG_FORMAT"] = self.inline_cedar_log_format

        return env_vars

    def load_from_env(self):
        self.image = os.getenv("OPAL_CLIENT_IMAGE", "opal_client_debug_local")
        self.container_name = os.getenv("OPAL_CLIENT_CONTAINER_NAME", "opal_client")
        self.port = os.getenv("OPAL_CLIENT_PORT", utils.find_available_port(7000))
        self.opal_server_url = os.getenv("OPAL_SERVER_URL", "http://opal_server:7002")
        self.opa_port = os.getenv("OPA_PORT", 8181)
        self.tests_debug = os.getenv("OPAL_TESTS_DEBUG", "true")
        self.log_diagnose = os.getenv("LOG_DIAGNOSE", "true")
        self.log_level = os.getenv("OPAL_LOG_LEVEL", "DEBUG")
        self.log_format_include_pid = os.getenv("OPAL_LOG_FORMAT_INCLUDE_PID", "true")
        self.should_report_on_data_updates = os.getenv(
            "OPAL_SHOULD_REPORT_ON_DATA_UPDATES", "true"
        )
        self.default_update_callbacks = os.getenv("OPAL_DEFAULT_UPDATE_CALLBACKS", None)
        self.opa_health_check_policy_enabled = os.getenv(
            "OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED", "true"
        )
        self.client_token = os.getenv("OPAL_CLIENT_TOKEN", None)
        self.auth_jwt_audience = os.getenv(
            "OPAL_AUTH_JWT_AUDIENCE", "https://api.opal.ac/v1/"
        )
        self.auth_jwt_issuer = os.getenv("OPAL_AUTH_JWT_ISSUER", "https://opal.ac/")
        self.statistics_enabled = os.getenv("OPAL_STATISTICS_ENABLED", "true")
        self.debug_enabled = os.getenv("OPAL_DEBUG_ENABLED", False)
        self.debug_port = os.getenv("CLIENT_DEBUG_PORT", 6678)
        self.policy_store_url = os.getenv("OPAL_POLICY_STORE_URL", None)

        self.policy_store_type = os.getenv("OPAL_POLICY_STORE_TYPE", "OPA")

        self.uvicorn_asgi_app = os.getenv("UVICORN_ASGI_APP", "opal_client.main:app")

        self.iniline_cedar_enabled = os.getenv("OPAL_INILINE_CEDAR_ENABLED", "false")
        self.inline_cedar_exec_path = os.getenv(
            "OPAL_INLINE_CEDAR_EXEC_PATH", "/cedar/cedar-agent"
        )
        self.inline_cedar_config = os.getenv(
            "OPAL_INLINE_CEDAR_CONFIG", '{"addr": "0.0.0.0:8180"}'
        )
        self.inline_cedar_log_format = os.getenv("OPAL_INLINE_CEDAR_LOG_FORMAT", "http")

        self.inline_opa_enabled = os.getenv("OPAL_INLINE_OPA_ENABLED", "true")
        self.inline_opa_exec_path = os.getenv("OPAL_INLINE_OPA_EXEC_PATH", "/opa/opa")
        self.inline_opa_config = os.getenv(
            "OPAL_INLINE_OPA_CONFIG", '{"addr": "0.0.0.0:8181"}'
        )
        self.inline_opa_log_format = os.getenv("OPAL_INLINE_OPA_LOG_FORMAT", "http")
        self.topics = os.getenv("OPAL_DATA_TOPICS", "policy_data")
