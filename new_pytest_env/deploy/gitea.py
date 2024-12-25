import docker
import time
import os
from testcontainers.core.generic import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.utils import is_arm, setup_logger


logger = setup_logger(__name__)

class gitea(DockerContainer):    
    def __init__(self, GITEA_CONTAINER_NAME, GITEA_3000_PORT, GITEA_2222_PORT, GITEA_IMAGE, USER_UID, USER_GID, NETWORK: Network, user_name: str = "permitAdmin", email:str = "admin@permit.io", password:str = "Aa123456") -> None:


        self.name = GITEA_CONTAINER_NAME
        self.port_3000 = GITEA_3000_PORT
        self.port_2222 = GITEA_2222_PORT
        self.image = GITEA_IMAGE
        self.uid = USER_UID
        self.gid = USER_GID
        #self.network = NETWORK

        self.temp_dir = "/home/ari/Desktop/opal/new_pytest_env/temp"

        self.user_name = user_name
        self.email = email
        self.password = password

        self.params_check()

        super().__init__(image=self.image)
        
        self.deploy_gitea()

        self.start()

        self.wait_for_gitea()

        self.create_gitea_user()

        self.create_gitea_admin_token()
                

    

    def params_check(self):
        if not self.name:
            raise ValueError("Missing 'name'")
        if not self.port_3000:
            raise ValueError("Missing 'port_3000'")
        if not self.port_2222:
            raise ValueError("Missing 'port_2222'")
        if not self.image:
            raise ValueError("Missing 'image'")
        if not self.uid:
            raise ValueError("Missing 'uid'")
        if not self.gid:
            raise ValueError("Missing 'gid'")
        #if not self.network:
            #raise ValueError("Missing 'network'")
            
        
        
        
        
        
    # Wait for Gitea to initialize
    def is_gitea_ready(self):
        stdout_logs, stderr_logs = self.get_logs()
        logs = stdout_logs.decode("utf-8") + stderr_logs.decode("utf-8")
        return "Listen: http://0.0.0.0:3000" in logs

    def wait_for_gitea(self):
        for _ in range(30):
            if self.is_gitea_ready():
                break
            time.sleep(1)
        else:
            raise RuntimeError("Gitea initialization timeout")

    def create_gitea_user(self):
        # Commands to create an admin user and generate a token
        create_user_command = (
            f"/usr/local/bin/gitea admin user create "
            f"--admin --username {self.user_name} "
            f"--email {self.email} "
            f"--password {self.password} "
            f"--must-change-password=false"
        )
        # Execute commands inside the container
        self.exec(create_user_command)

    def create_gitea_admin_token(self):
        global gitea_container, create_token_command, TEMP_DIR, ACCESS_TOKEN


        create_token_command = (
            f"/usr/local/bin/gitea admin user generate-access-token "
            f"--username {self.user_name} --raw --scopes all"
        )

        token_result = self.exec(create_token_command).output.decode("utf-8").strip()

        if not token_result:
            raise RuntimeError("Failed to create an access token.")

        # Save the token to a file
        TOKEN_FILE = os.path.join(self.temp_dir, "gitea_access_token.tkn")
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(token_result)
        
        ACCESS_TOKEN = token_result

    def deploy_gitea(self):
        """
        Deploys Gitea in a Docker container and initializes configuration variables.
        """


        self.with_env("USER_UID", self.uid)
        self.with_env("USER_GID", self.gid)
        self.with_env("DB_TYPE", "sqlite3")
        self.with_env("DB_PATH", "./")
        self.with_env("INSTALL_LOCK", "true")

        #self.with_network(self.network)

        self.with_name(self.name)

        self.with_bind_ports(3000, self.port_3000)
        self.with_bind_ports(2222, self.port_2222)
