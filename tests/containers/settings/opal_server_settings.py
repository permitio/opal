
import os
from secrets import token_hex

from testcontainers.core.utils import setup_logger

from tests import utils

class OpalServerSettings:
    def __init__(
        self,
        container_name: str = None,
        port: int = None,
        uvicorn_workers: str = None,
        policy_repo_url: str = None,
        polling_interval: str = None,
        private_key: str = None,
        public_key: str = None,
        master_token: str = None,
        data_topics: str = None,
        auth_audience: str = None,
        auth_issuer: str = None,
        tests_debug: bool = False,
        log_diagnose: str = None,
        log_level: str = None,
        log_format_include_pid: bool = None,
        statistics_enabled: bool = None,
        debug_enabled: bool = None,
        debug_port: int = None,
        auth_private_key_passphrase: str = None,
        policy_repo_main_branch: str = None,
        image: str = None,
        broadcast_uri: str = None,
        container_index: int = 1,
        **kwargs):
    
        """
        Initialize the OPAL Server with the provided parameters.

        :param image: Docker image for the OPAL server.
        :param container_name: Name of the Docker container.
        :param network_name: Name of the Docker network to attach.
        :param port: Exposed port for the OPAL server.
        :param uvicorn_workers: Number of Uvicorn workers.
        :param policy_repo_url: URL of the policy repository.
        :param polling_interval: Polling interval for the policy repository.
        :param private_key: SSH private key for authentication.
        :param public_key: SSH public key for authentication.
        :param master_token: Master token for OPAL authentication.
        :param data_topics: Data topics for OPAL configuration.
        :param broadcast_uri: Optional URI for the broadcast channel.
        :param auth_audience: Optional audience for authentication.
        :param auth_issuer: Optional issuer for authentication.
        :param tests_debug: Optional flag for tests debug mode.
        :param log_diagnose: Optional flag for log diagnosis.
        :param log_level: Optional log level for the OPAL server.
        :param log_format_include_pid: Optional flag for including PID in log format.
        :param statistics_enabled: Optional flag for enabling statistics.
        :param debug_enabled: Optional flag for enabling debug mode with debugpy.
        :param debug_port: Optional port for debugpy.
        :param auth_private_key_passphrase: Optional passphrase for the private key.
        :param policy_repo_main_branch: Optional main branch for the policy repository.
        :param container_index: Optional index for the container.
        :param kwargs: Additional keyword arguments.
        """
        
        self.loger = setup_logger(__name__)

        self.load_from_env()

        self.image = image if image else self.image
        self.container_name = container_name if container_name else self.container_name
        self.port = port if port else self.port
        self.uvicorn_workers = uvicorn_workers if uvicorn_workers else self.uvicorn_workers
        self.policy_repo_url = policy_repo_url if policy_repo_url else self.policy_repo_url
        self.polling_interval = polling_interval if polling_interval else self.polling_interval
        self.private_key = private_key if private_key else self.private_key
        self.public_key = public_key if public_key else self.public_key
        self.master_token = master_token if master_token else self.master_token
        self.data_topics = data_topics if data_topics else self.data_topics
        self.broadcast_uri = broadcast_uri if broadcast_uri else self.broadcast_uri
        self.auth_audience = auth_audience if auth_audience else self.auth_audience
        self.auth_issuer = auth_issuer if auth_issuer else self.auth_issuer
        self.tests_debug = tests_debug if tests_debug else self.tests_debug
        self.log_diagnose = log_diagnose if log_diagnose else self.log_diagnose
        self.log_level = log_level if log_level else self.log_level
        self.log_format_include_pid = log_format_include_pid if log_format_include_pid else self.log_format_include_pid
        self.statistics_enabled = statistics_enabled if statistics_enabled else self.statistics_enabled
        self.debugEnabled = debug_enabled if debug_enabled else self.debugEnabled
        self.debug_port = debug_port if debug_port else self.debug_port
        self.auth_private_key_passphrase = auth_private_key_passphrase if auth_private_key_passphrase else self.auth_private_key_passphrase
        self.policy_repo_main_branch = policy_repo_main_branch if policy_repo_main_branch else self.policy_repo_main_branch
        self.container_index = container_index if container_index else self.container_index
        self.__dict__.update(kwargs)

        if(container_index > 1):
            self.port = self.port + container_index - 1
            self.debug_port = self.debug_port + container_index - 1
    
        self.validate_dependencies()
    
    def validate_dependencies(self):
        """Validate required dependencies before starting the server."""
        if not self.policy_repo_url:
            raise ValueError("OPAL_POLICY_REPO_URL is required.")
        if not self.private_key or not self.public_key:
            raise ValueError("SSH private and public keys are required.")
        if not self.master_token:
            raise ValueError("OPAL master token is required.")
        self.loger.info("Dependencies validated successfully.")
        
    def getEnvVars(self):
               
        # Configure environment variables
        
        env_vars = {
            "UVICORN_NUM_WORKERS": self.uvicorn_workers,
            "OPAL_POLICY_REPO_URL": self.policy_repo_url,
            "OPAL_POLICY_REPO_MAIN_BRANCH": self.policy_repo_main_branch,
            "OPAL_POLICY_REPO_POLLING_INTERVAL": self.polling_interval,
            "OPAL_AUTH_PRIVATE_KEY": self.private_key,
            "OPAL_AUTH_PUBLIC_KEY": self.public_key,
            "OPAL_AUTH_MASTER_TOKEN": self.master_token,
            "OPAL_DATA_CONFIG_SOURCES": f"""{{"config":{{"entries":[{{"url":"http://{self.container_name}:{self.port}/policy-data","topics":["{self.data_topics}"],"dst_path":"/static"}}]}}}}""",
            "OPAL_LOG_FORMAT_INCLUDE_PID": self.log_format_include_pid, 
            "OPAL_STATISTICS_ENABLED": self.statistics_enabled, 
            "OPAL_AUTH_JWT_AUDIENCE": self.auth_audience,
            "OPAL_AUTH_JWT_ISSUER": self.auth_issuer,
        }

        if(self.tests_debug):
            env_vars["LOG_DIAGNOSE"] = self.log_diagnose
            env_vars["OPAL_LOG_LEVEL"] = self.log_level

        if(self.auth_private_key_passphrase):
            env_vars["OPAL_AUTH_PRIVATE_KEY_PASSPHRASE"] = self.auth_private_key_passphrase

        if self.broadcast_uri:
            env_vars["OPAL_BROADCAST_URI"] = self.broadcast_uri

        return env_vars
    
    def load_from_env(self):

        self.image = os.getenv("OPAL_SERVER_IMAGE", "opal_server_debug_local")
        self.container_name = os.getenv("OPAL_SERVER_CONTAINER_NAME", None)
        self.port = os.getenv("OPAL_SERVER_PORT", utils.find_available_port(7002))
        self.uvicorn_workers = os.getenv("OPAL_SERVER_UVICORN_WORKERS", "1")
        self.policy_repo_url = os.getenv("OPAL_POLICY_REPO_URL", None)
        self.polling_interval = os.getenv("OPAL_POLICY_REPO_POLLING_INTERVAL", "30")
        self.private_key = os.getenv("OPAL_AUTH_PRIVATE_KEY", None)
        self.public_key = os.getenv("OPAL_AUTH_PUBLIC_KEY", None)
        self.master_token = os.getenv("OPAL_AUTH_MASTER_TOKEN", token_hex(16))
        self.data_topics = os.getenv("OPAL_DATA_TOPICS", "policy_data")
        self.broadcast_uri = os.getenv("OPAL_BROADCAST_URI", None)
        self.auth_audience = os.getenv("OPAL_AUTH_JWT_AUDIENCE", "https://api.opal.ac/v1/")        
        self.auth_issuer = os.getenv("OPAL_AUTH_JWT_ISSUER", "https://opal.ac/")
        self.tests_debug = os.getenv("OPAL_TESTS_DEBUG", "true")        
        self.log_diagnose = os.getenv("LOG_DIAGNOSE", "true")        
        self.log_level = os.getenv("OPAL_LOG_LEVEL", "DEBUG")     
        self.log_format_include_pid = os.getenv("OPAL_LOG_FORMAT_INCLUDE_PID", "true")    
        self.statistics_enabled = os.getenv("OPAL_STATISTICS_ENABLED", "true")
        self.debugEnabled = os.getenv("OPAL_DEBUG_ENABLED", "false")        
        self.auth_private_key_passphrase = os.getenv("OPAL_AUTH_PRIVATE_KEY_PASSPHRASE", None)        
        self.policy_repo_main_branch = os.getenv("OPAL_POLICY_REPO_MAIN_BRANCH", "master")  
        self.debug_port = os.getenv("SERVER_DEBUG_PORT", 5678)

        if not self.private_key or not self.public_key:
            self.private_key, self.public_key = utils.generate_ssh_key_pair() 