import os

from tests import utils


class CedarSettings:
    def __init__(
        self,
        client_token: str = None,
        container_name: str = None,
        port: int = None,
        opal_server_url: str = None,
        should_report_on_data_updates: str = None,
        log_format_include_pid: str = None,
        inline_opa_log_format: str = None,
        tests_debug: bool = False,
        log_diagnose: str = None,
        log_level: str = None,
        debug_enabled: bool = None,
        debug_port: int = None,
        image: str = None,
        opa_port: int = None,
        default_update_callbacks: str = None,
        opa_health_check_policy_enabled: str = None,
        auth_jwt_audience: str = None,
        auth_jwt_issuer: str = None,
        statistics_enabled: str = None,
        container_index: int = 1,
        **kwargs
    ):
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
        self.inline_opa_log_format = (
            inline_opa_log_format
            if inline_opa_log_format
            else self.inline_opa_log_format
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

        if self.container_index > 1:
            self.opa_port += self.container_index - 1
            # self.port += self.container_index - 1
            self.debug_port += self.container_index - 1

        self.validate_dependencies()

    def validate_dependencies(self):
        if not self.image:
            raise ValueError("OPAL_CLIENT_IMAGE is required.")
        if not self.container_name:
            raise ValueError("OPAL_CLIENT_CONTAINER_NAME is required.")
        if not self.opal_server_url:
            raise ValueError("OPAL_SERVER_URL is required.")

    def getEnvVars(self):
        env_vars = {
            "OPAL_SERVER_URL": self.opal_server_url,
            "OPAL_LOG_FORMAT_INCLUDE_PID": self.log_format_include_pid,
            "OPAL_INLINE_OPA_LOG_FORMAT": self.inline_opa_log_format,
            "OPAL_SHOULD_REPORT_ON_DATA_UPDATES": self.should_report_on_data_updates,
            "OPAL_DEFAULT_UPDATE_CALLBACKS": self.default_update_callbacks,
            "OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED": self.opa_health_check_policy_enabled,
            "OPAL_CLIENT_TOKEN": self.client_token,
            "OPAL_AUTH_JWT_AUDIENCE": self.auth_jwt_audience,
            "OPAL_AUTH_JWT_ISSUER": self.auth_jwt_issuer,
            "OPAL_STATISTICS_ENABLED": self.statistics_enabled,
            # TODO: make not hardcoded
            "OPAL_DATA_TOPICS": "policy_data",
        }

        if self.tests_debug:
            env_vars["LOG_DIAGNOSE"] = self.log_diagnose
            env_vars["OPAL_LOG_LEVEL"] = self.log_level

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
        self.inline_opa_log_format = os.getenv("OPAL_INLINE_OPA_LOG_FORMAT", "http")
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

    # TODO: Clean up this code
    # # Define environment variables for configuration
    # ENV OPAL_POLICY_STORE_TYPE=CEDAR
    # ENV OPAL_INLINE_CEDAR_ENABLED=true
    # ENV OPAL_INLINE_CEDAR_EXEC_PATH=/cedar/cedar-agent
    # ENV OPAL_INLINE_CEDAR_CONFIG='{"addr": "0.0.0.0:8180"}'
    # ENV OPAL_POLICY_STORE_URL=http://localhost:8180

    # # Expose Cedar agent port
    # EXPOSE 8180
