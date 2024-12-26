import codecs
import docker
import time
import os
import requests
import shutil

from git import GitCommandError, Repo
from testcontainers.core.generic import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.utils import setup_logger


logger = setup_logger(__name__)

class GiteaContainer(DockerContainer):
    def __init__(
        self,
        GITEA_CONTAINER_NAME: str,
        repo_name: str,
        temp_dir: str,
        data_dir: str,
        GITEA_3000_PORT: int = 3000,
        GITEA_2222_PORT: int = 2222,
        GITEA_IMAGE: str = "gitea/gitea:latest-rootless",
        USER_UID: int = 1000,
        USER_GID: int = 1000,
        NETWORK: Network = None,
        user_name: str = "permitAdmin",
        email: str = "admin@permit.io",
        password: str = "Aa123456",
        gitea_base_url: str = "http://localhost:3000",
        **kwargs
    ):
        """
        Initialize the Gitea Docker container and related parameters.

        :param GITEA_CONTAINER_NAME: Name of the Gitea container
        :param repo_name: Name of the repository
        :param temp_dir: Path to the temporary directory for files
        :param data_dir: Path to the data directory for persistent files
        :param GITEA_3000_PORT: Optional - Port for Gitea HTTP access
        :param GITEA_2222_PORT: Optional - Port for Gitea SSH access
        :param GITEA_IMAGE: Optional - Docker image for Gitea
        :param USER_UID: Optional - User UID for Gitea
        :param USER_GID: Optional - User GID for Gitea
        :param NETWORK: Optional - Optional Docker network for the container
        :param user_name: Optional - Default admin username for Gitea
        :param email: Optional - Default admin email for Gitea
        :param password: Optional - Default admin password for Gitea
        :param gitea_base_url: Optional - Base URL for the Gitea instance
        """
        self.name = GITEA_CONTAINER_NAME
        self.repo_name = repo_name  # Repository name
        self.port_3000 = GITEA_3000_PORT
        self.port_2222 = GITEA_2222_PORT
        self.image = GITEA_IMAGE
        self.uid = USER_UID
        self.gid = USER_GID
        self.network = NETWORK

        self.user_name = user_name
        self.email = email
        self.password = password
        self.gitea_base_url = gitea_base_url

        self.temp_dir = os.path.abspath(temp_dir)  # Temporary directory for cloned repositories and files
        self.data_dir = data_dir  # Data directory for persistent files (e.g., RBAC file)
        
        self.access_token = None  # Optional, can be set later

        # Validate required parameters
        self.params_check()

        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        # Initialize the Docker container
        super().__init__(image=self.image, kwargs=kwargs)

        # Configure container environment variables
        self.with_env("USER_UID", self.uid)
        self.with_env("USER_GID", self.gid)
        self.with_env("DB_TYPE", "sqlite3")
        self.with_env("INSTALL_LOCK", "true")

        # Set container name and ports
        self.with_name(self.name)
        self.with_bind_ports(3000, self.port_3000)
        self.with_bind_ports(2222, self.port_2222)

        # Set container lifecycle properties
        self.with_kwargs(auto_remove=False, restart_policy={"Name": "always"})
        

        # Attach to the specified Docker network if provided
        if self.network:
            self.with_network(self.network)


    def params_check(self):
        """Validate required parameters."""
        required_params = [self.name, self.port_3000, self.port_2222, self.image, self.uid, self.gid]
        if not all(required_params):
            raise ValueError("Missing required parameters for Gitea container initialization.")

    def is_gitea_ready(self):
        """Check if Gitea is ready by inspecting logs."""
        stdout_logs, stderr_logs = self.get_logs()
        logs = stdout_logs.decode("utf-8") + stderr_logs.decode("utf-8")
        return "Listen: http://0.0.0.0:3000" in logs

    def wait_for_gitea(self, timeout: int = 30):
        """Wait for Gitea to initialize within a timeout period."""
        for _ in range(timeout):
            if self.is_gitea_ready():
                logger.info("Gitea is ready.")
                return
            time.sleep(1)
        raise RuntimeError("Gitea initialization timeout.")

    def create_gitea_user(self):
        """Create an admin user in the Gitea instance."""
        create_user_command = (
            f"/usr/local/bin/gitea admin user create "
            f"--admin --username {self.user_name} "
            f"--email {self.email} "
            f"--password {self.password} "
            f"--must-change-password=false"
        )
        result = self.exec(create_user_command)
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create Gitea user: {result.output.decode('utf-8')}")

    def create_gitea_admin_token(self):
        """Generate an admin access token for the Gitea instance."""
        create_token_command = (
            f"/usr/local/bin/gitea admin user generate-access-token "
            f"--username {self.user_name} --raw --scopes all"
        )
        result = self.exec(create_token_command)
        token_result = result.output.decode("utf-8").strip()
        if not token_result:
            raise RuntimeError("Failed to create an access token.")

        # Save the token to a file
        TOKEN_FILE = os.path.join(self.temp_dir, "gitea_access_token.tkn")
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(token_result)

        logger.info(f"Access token saved to {TOKEN_FILE}")
        return token_result

    def deploy_gitea(self):
        """Deploy Gitea container and initialize configuration."""
        logger.info("Deploying Gitea container...")
        self.start()
        self.wait_for_gitea()
        self.create_gitea_user()
        self.access_token = self.create_gitea_admin_token()
        logger.info(f"Gitea deployed successfully. Admin access token: {self.access_token}")

    def exec(self, command: str):
        """Execute a command inside the container."""
        logger.info(f"Executing command: {command}")
        exec_result = self.get_wrapped_container().exec_run(command)
        if exec_result.exit_code != 0:
            raise RuntimeError(f"Command failed with exit code {exec_result.exit_code}: {exec_result.output.decode('utf-8')}")
        return exec_result


    def repo_exists(self):
        url = f"{self.gitea_base_url}/repos/{self.user_name}/{self.repo_name}"
        headers = {"Authorization": f"token {self.access_token}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Repository '{self.repo_name}' already exists.")
            return True
        elif response.status_code == 404:
            logger.info(f"Repository '{self.repo_name}' does not exist.")
            return False
        else:
            logger.error(f"Failed to check repository: {response.status_code} {response.text}")
            response.raise_for_status()

    def create_gitea_repo(self, description="", private=False, auto_init=True, default_branch="master"):
        url = f"{self.gitea_base_url}/api/v1/user/repos"
        headers = {
            "Authorization": f"token {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": self.repo_name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
            "default_branch": default_branch
        }
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            logger.info("Repository created successfully!")
            return response.json()
        else:
            logger.error(f"Failed to create repository: {response.status_code} {response.text}")
            response.raise_for_status()

    def clone_repo_with_gitpython(self, clone_directory):
        repo_url = f"{self.gitea_base_url}/{self.user_name}/{self.repo_name}.git"
        if self.access_token:
            repo_url = f"http://{self.user_name}:{self.access_token}@{self.gitea_base_url.split('://')[1]}/{self.user_name}/{self.repo_name}.git"
        try:
            if os.path.exists(clone_directory):
                logger.info(f"Directory '{clone_directory}' already exists. Deleting it...")
                shutil.rmtree(clone_directory)
            Repo.clone_from(repo_url, clone_directory)
            logger.info(f"Repository '{self.repo_name}' cloned successfully into '{clone_directory}'.")
        except Exception as e:
            logger.error(f"Failed to clone repository '{self.repo_name}': {e}")

    def reset_repo_with_rbac(self, repo_directory, source_rbac_file):
        try:
            if not os.path.exists(repo_directory):
                raise FileNotFoundError(f"Repository directory '{repo_directory}' does not exist.")

            git_dir = os.path.join(repo_directory, ".git")
            if not os.path.exists(git_dir):
                raise FileNotFoundError(f"The directory '{repo_directory}' is not a valid Git repository (missing .git folder).")

            repo = Repo(repo_directory)

            # Get the default branch name
            default_branch = self.get_default_branch(repo)
            if not default_branch:
                raise ValueError("Could not determine the default branch name.")

            # Ensure we are on the default branch
            if repo.active_branch.name != default_branch:
                repo.git.checkout(default_branch)

            # Remove other branches
            branches = [branch.name for branch in repo.branches if branch.name != default_branch]
            for branch in branches:
                repo.git.branch("-D", branch)

            # Reset repository content
            for item in os.listdir(repo_directory):
                item_path = os.path.join(repo_directory, item)
                if os.path.basename(item_path) == ".git":
                    continue
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)

            # Copy RBAC file
            destination_rbac_path = os.path.join(repo_directory, "rbac.rego")
            shutil.copy2(source_rbac_file, destination_rbac_path)

            # Stage and commit changes
            repo.git.add(all=True)
            repo.index.commit("Reset repository to only include 'rbac.rego'")

            logger.info(f"Repository reset successfully. 'rbac.rego' is the only file and changes are committed.")
        except Exception as e:
            logger.error(f"Error resetting repository: {e}")

    def get_default_branch(self, repo):
        try:
            return repo.git.symbolic_ref("refs/remotes/origin/HEAD").split("/")[-1]
        except Exception as e:
            logger.error(f"Error determining default branch: {e}")
            return None

    def push_repo_to_remote(self, repo_directory):
        try:
            repo = Repo(repo_directory)

            # Get the default branch name
            default_branch = self.get_default_branch(repo)
            if not default_branch:
                raise ValueError("Could not determine the default branch name.")

            # Ensure we are on the default branch
            if repo.active_branch.name != default_branch:
                repo.git.checkout(default_branch)

            # Check if remote origin exists
            if "origin" not in [remote.name for remote in repo.remotes]:
                raise ValueError("No remote named 'origin' found in the repository.")

            # Push changes to the default branch
            repo.remotes.origin.push(refspec=f"{default_branch}:{default_branch}")
            logger.info("Changes pushed to remote repository successfully.")
        except Exception as e:
            logger.error(f"Error pushing changes to remote: {e}")

    def cleanup_local_repo(self, repo_directory):
        try:
            if os.path.exists(repo_directory):
                shutil.rmtree(repo_directory)
                logger.info(f"Local repository '{repo_directory}' has been cleaned up.")
            else:
                logger.info(f"Local repository '{repo_directory}' does not exist. No cleanup needed.")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def init_repo(self):
        try:
            # Set paths for source RBAC file and clone directory
            source_rbac_file = os.path.join(self.data_dir, "rbac.rego")  # Use self.data_dir for source RBAC file
            clone_directory = os.path.join(self.temp_dir, f"{self.repo_name}-clone")  # Use self.repo_name

            # Check if the repository exists
            if not self.repo_exists():
                # Create the repository if it doesn't exist
                self.create_gitea_repo(
                    description="This is a test repository created via API.",
                    private=False
                )

            # Clone the repository
            self.clone_repo_with_gitpython(clone_directory=clone_directory)

            # Reset the repository with RBAC
            self.reset_repo_with_rbac(repo_directory=clone_directory, source_rbac_file=source_rbac_file)

            # Push the changes to the remote repository
            self.push_repo_to_remote(repo_directory=clone_directory)

            # Clean up the local repository
            self.cleanup_local_repo(repo_directory=clone_directory)

            logger.info("Repository initialization completed successfully.")
        except Exception as e:
            logger.error(f"Error during repository initialization: {e}")

    # Prepare the directory
    def prepare_directory(self, path):
        """Prepare the directory by cleaning up any existing content."""
        if os.path.exists(path):
            shutil.rmtree(path)  # Remove existing directory
        os.makedirs(path)  # Create a new directory

    # Clone and push changes
    def clone_and_update(self, branch, file_name, file_content, CLONE_DIR, authenticated_url, COMMIT_MESSAGE):
        """Clone the repository, update the specified branch, and push changes."""
        self.prepare_directory(CLONE_DIR)  # Clean up and prepare the directory
        print(f"Processing branch: {branch}")

        # Clone the repository for the specified branch
        print(f"Cloning branch {branch}...")
        repo = Repo.clone_from(authenticated_url, CLONE_DIR, branch=branch)

        # Create or update the specified file with the provided content
        file_path = os.path.join(CLONE_DIR, file_name)
        with open(file_path, "w") as f:
            f.write(file_content)

        # Stage the changes
        print(f"Staging changes for branch {branch}...")
        repo.git.add(A=True)  # Add all changes

        # Commit the changes if there are modifications
        if repo.is_dirty():
            print(f"Committing changes for branch {branch}...")
            repo.index.commit(COMMIT_MESSAGE)

        # Push changes to the remote repository
        print(f"Pushing changes for branch {branch}...")
        try:
            repo.git.push(authenticated_url, branch)
        except GitCommandError as e:
            print(f"Error pushing branch {branch}: {e}")

    # Cleanup function
    def cleanup(self, CLONE_DIR):
        """Remove the temporary clone directory."""
        if os.path.exists(CLONE_DIR):
            print("Cleaning up temporary directory...")
            shutil.rmtree(CLONE_DIR)

    def update_branch(self, branch, file_name, file_content):
        temp_dir = self.temp_dir

        # Decode escape sequences in the file content
        file_content = codecs.decode(file_content, 'unicode_escape')

        GITEA_REPO_URL = f"http://localhost:3000/{self.user_name}/{self.repo_name}.git"
        USER_NAME = self.user_name
        PASSWORD = self.password
        CLONE_DIR = os.path.join(temp_dir, "branch_update")
        COMMIT_MESSAGE = "Automated update commit"

        # Append credentials to the repository URL
        authenticated_url = GITEA_REPO_URL.replace("http://", f"http://{USER_NAME}:{PASSWORD}@")

        try:
            self.clone_and_update(branch, file_name, file_content, CLONE_DIR, authenticated_url, COMMIT_MESSAGE)
            print("Operation completed successfully.")
        finally:
            # Ensure cleanup is performed regardless of success or failure
            self.cleanup(CLONE_DIR)