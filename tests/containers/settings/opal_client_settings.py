
import os

class OpalClientSettings:
    def __init__(
            self, 
            container_name: str = None,
            network_name: str = None,
            tests_debug: bool = False,
            log_diagnose: str = None,
            log_level: str = None,
            debug_enabled: bool = None,
            image: str = None,
            **kwargs):

        self.load_from_env()

        self.image = image if image else self.image
        self.container_name = container_name if container_name else self.container_name
        self.network_name = network_name if network_name else self.network_name
        self.tests_debug = tests_debug if tests_debug else self.tests_debug
        self.log_diagnose = log_diagnose if log_diagnose else self.log_diagnose
        self.log_level = log_level if log_level else self.log_level
        self.debug_enabled = debug_enabled if debug_enabled else self.debug_enabled
        self.__dict__.update(kwargs)

        self.validate_dependencies()

    def validate_dependencies(self):
        pass

    def getEnvVars(self):
        
        env_vars = {  
            "OPAL_LOG_FORMAT_INCLUDE_PID": self.log_format_include_pid,
            "OPAL_INLINE_OPA_LOG_FORMAT": self.inline_opa_log_format,
            "OPAL_SHOULD_REPORT_ON_DATA_UPDATES": self.should_report_on_data_updates,
            "OPAL_DEFAULT_UPDATE_CALLBACKS": self.default_update_callbacks,
            "OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED": self.opa_health_check_policy_enabled,
            "OPAL_CLIENT_TOKEN": self.client_token,
            "OPAL_AUTH_PUBLIC_KEY": self.auth_public_key,
            "OPAL_AUTH_JWT_AUDIENCE": self.auth_jwt_audience,
            "OPAL_AUTH_JWT_ISSUER": self.auth_jwt_issuer,
            "OPAL_STATISTICS_ENABLED": self.statistics_enabled,
        }
        
        if(self.settings.tests_debug):
            env_vars["LOG_DIAGNOSE"] = self.log_diagnose
            env_vars["OPAL_LOG_LEVEL"] = self.log_level

        return env_vars
    
    def load_from_env(self):    

        self.image = os.getenv("OPAL_CLIENT_IMAGE", "opal_client_debug_local")
        self.container_name = os.getenv("OPAL_CLIENT_CONTAINER_NAME", self.container_name)
        self.network_name = os.getenv("OPAL_CLIENT_NETWORK_NAME", self.network_name)
        self.tests_debug = os.getenv("OPAL_TESTS_DEBUG", "true")
        self.log_diagnose = os.getenv("LOG_DIAGNOSE", "true")
        self.log_level = os.getenv("OPAL_LOG_LEVEL", "DEBUG")
        self.log_format_include_pid = os.getenv("OPAL_LOG_FORMAT_INCLUDE_PID", "true")
        self.inline_opa_log_format = os.getenv("OPAL_INLINE_OPA_LOG_FORMAT", "false")
        self.should_report_on_data_updates = os.getenv("OPAL_SHOULD_REPORT_ON_DATA_UPDATES", "true")
        self.default_update_callbacks = os.getenv("OPAL_DEFAULT_UPDATE_CALLBACKS", "true")
        self.opa_health_check_policy_enabled = os.getenv("OPAL_OPA_HEALTH_CHECK_POLICY_ENABLED", "true")
        self.client_token = os.getenv("OPAL_CLIENT_TOKEN", None)
        self.auth_public_key = os.getenv("OPAL_AUTH_PUBLIC_KEY", None)
        self.auth_jwt_audience = os.getenv("OPAL_AUTH_JWT_AUDIENCE", "https://api.opal.ac/v1/")
        self.auth_jwt_issuer = os.getenv("OPAL_AUTH_JWT_ISSUER", "https://opal.ac/")
        self.statistics_enabled = os.getenv("OPAL_STATISTICS_ENABLED", "true")

        