
import os
from testcontainers.core.utils import setup_logger


class GiteaSettings:
    def __init__(
            self, 
            container_name: str = None,
            network_name: str = None, 
            repo_name: str = None, 
            temp_dir: str = None, 
            data_dir: str = None, 
            GITEA_3000_PORT: int = None, 
            GITEA_2222_PORT: int = None, 
            USER_UID: int = None, 
            USER_GID: int = None, 
            username: str = None,
            email: str = None,   
            password: str = None, 
            gitea_base_url: str = None, 
            gitea_container_port: int = None,
            network_aliases: str = None,
            image: str = None, 
            **kwargs):

        """
        Initialize the Gitea Docker container and related parameters.

        :param container_name: Name of the Gitea container
        :param network_name: Optional - Optional Docker network for the container
        :param repo_name: Name of the repository
        :param temp_dir: Path to the temporary directory for files
        :param data_dir: Path to the data directory for persistent files
        :param GITEA_3000_PORT: Optional - Port for Gitea HTTP access
        :param GITEA_2222_PORT: Optional - Port for Gitea SSH access
        :param image: Optional - Docker image for Gitea
        :param USER_UID: Optional - User UID for Gitea
        :param USER_GID: Optional - User GID for Gitea
        :param username: Optional - Default admin username for Gitea
        :param email: Optional - Default admin email for Gitea
        :param password: Optional - Default admin password for Gitea
        :param gitea_base_url: Optional - Base URL for the Gitea instance
        """
         
        self.logger = setup_logger(__name__)

        self.load_from_env()
        
        self.image = image if image else self.image
        self.container_name = container_name if container_name else self.container_name
        self.repo_name = repo_name if repo_name else self.repo_name
        self.port_http = GITEA_3000_PORT if GITEA_3000_PORT else self.port_http
        self.port_2222 = GITEA_2222_PORT if GITEA_2222_PORT else self.port_2222
        self.uid = USER_UID if USER_UID else self.uid
        self.gid = USER_GID if USER_GID else self.gid
        self.network = network_name if network_name else self.network

        self.username = username if username else self.username
        self.email = email if email else self.email
        self.password = password if password else self.password
        self.gitea_base_url = gitea_base_url if gitea_base_url else self.gitea_base_url

        self.temp_dir = os.path.abspath(temp_dir)  if temp_dir else self.temp_dir
        self.data_dir = data_dir if data_dir else self.data_dir  # Data directory for persistent files (e.g., RBAC file)
        
        self.db_type = "sqlite3"  # Default to SQLite
        self.install_lock = "true"
        
        self.network_aliases = network_aliases if network_aliases else self.network_aliases

        self.access_token = None  # Optional, can be set later
        self.__dict__.update(kwargs)

    
        # Validate required parameters
        self.validate_dependencies()

    
    def validate_dependencies(self):
        """Validate required parameters."""
        required_params = [self.container_name, self.port_http, self.port_2222, self.image, self.uid, self.gid]
        if not all(required_params):
            raise ValueError("Missing required parameters for Gitea container initialization.")

    def getEnvVars(self):
        return {
            "GITEA_CONTAINER_NAME": self.container_name,
            "REPO_NAME": self.repo_name,
            "TEMP_DIR": self.temp_dir,
            "DATA_DIR": self.data_dir,
            "GITEA_3000_PORT": self.port_http,
            "GITEA_2222_PORT": self.port_2222,
            "USER_UID": self.uid,
            "USER_GID": self.gid,
            "NETWORK": self.network,
            "username": self.username,
            "EMAIL": self.email,
            "PASSWORD": self.password,
            "GITEA_BASE_URL": self.gitea_base_url,
            "GITEA_IMAGE": self.image,
            "DB_TYPE": self.db_type, 
            "INSTALL_LOCK": self.install_lock
        }   
    
    def load_from_env(self):
        self.image = os.getenv("GITEA_IMAGE", "gitea/gitea:latest-rootless")
        self.container_name = os.getenv("GITEA_CONTAINER_NAME", "gitea")
        self.repo_name = os.getenv("REPO_NAME", "permit")
        self.temp_dir = os.getenv("TEMP_DIR", "/tmp/permit")
        self.data_dir = os.getenv("DATA_DIR", "/tmp/data")
        self.port_http = int(os.getenv("GITEA_3000_PORT", 3000))                    
        self.port_2222 = int(os.getenv("GITEA_2222_PORT", 2222))
        self.uid = int(os.getenv("USER_UID", 1000))
        self.gid = int(os.getenv("USER_GID", 1000))
        self.network = os.getenv("NETWORK", "pytest_opal_network")
        self.username = os.getenv("username", "permitAdmin")
        self.email = os.getenv("EMAIL", "admin@permit.io")
        self.password = os.getenv("PASSWORD", "Aa123456")
        self.gitea_base_url = os.getenv("GITEA_BASE_URL", "http://localhost:3000")
        self.access_token = os.getenv("GITEA_ACCESS_TOKEN", None)
        self.network_aliases = os.getenv("NETWORK_ALIASES", "gitea")
        