import codecs
import os
import random
import shutil
import subprocess

import requests
from git import Repo
from github import Auth, Github

from tests import utils

# # Default values for OPAL variables
# OPAL_POLICY_REPO_URL=${OPAL_POLICY_REPO_URL:-git@github.com:iwphonedo/opal-example-policy-repo.git}
# OPAL_POLICY_REPO_MAIN_BRANCH=master
# OPAL_POLICY_REPO_SSH_KEY_PATH=${OPAL_POLICY_REPO_SSH_KEY_PATH:-~/.ssh/id_rsa}
# OPAL_POLICY_REPO_SSH_KEY=${OPAL_POLICY_REPO_SSH_KEY:-$(cat "$OPAL_POLICY_REPO_SSH_KEY_PATH")}


class GithubPolicyRepo:
    def __init__(
        self,
        temp_dir: str,
        owner: str | None = None,
        repo: str | None = None,
        password: str | None = None,
        github_pat: str | None = None,
        ssh_key_path: str | None = None,
        source_repo_owner: str | None = None,
        source_repo_name: str | None = None,
        should_fork: bool = False,
        webhook_secret: str | None = None,
        webhook_host: str | None = None,
        webhook_port: int | None = None,
    ):
        self.load_from_env()

        self.protocol = "git"
        self.host = "github.com"
        self.port = 22
        self.temp_dir = temp_dir

        self.owner = owner if owner else self.owner
        self.password = password if password else self.password
        self.github_pat = github_pat if github_pat else self.github_pat
        self.repo = repo if repo else self.repo

        self.source_repo_owner = (
            source_repo_owner if source_repo_owner else self.source_repo_owner
        )
        self.source_repo_name = (
            source_repo_name if source_repo_name else self.source_repo_name
        )

        self.local_repo_path = os.path.join(self.temp_dir, self.source_repo_name)
        self.ssh_key_path = ssh_key_path if ssh_key_path else self.ssh_key_path
        self.should_fork = should_fork
        self.webhook_secret = webhook_secret if webhook_secret else self.webhook_secret
        self.webhook_host = webhook_host if webhook_host else self.webhook_host
        self.webhook_port = webhook_port if webhook_port else self.webhook_port

        self.load_ssh_key()

    def load_from_env(self):
        self.owner = os.getenv("OPAL_TARGET_ACCOUNT", None)
        self.github_pat = os.getenv("OPAL_GITHUB_PAT", None)
        self.ssh_key_path = os.getenv(
            "OPAL_PYTEST_POLICY_REPO_SSH_KEY_PATH", "~/.ssh/id_rsa"
        )
        self.source_repo_owner = os.getenv("OPAL_SOURCE_ACCOUNT", "permitio")
        self.source_repo_name = os.getenv(
            "OPAL_SOURCE_REPO_NAME", "opal-example-policy-repo"
        )
        self.webhook_secret = os.getenv("OPAL_WEBHOOK_SECRET", "xxxxx")

    def load_ssh_key(self):
        if self.ssh_key_path.startswith("~"):
            self.ssh_key_path = os.path.expanduser("~/.ssh/id_rsa")

        if not os.path.exists(self.ssh_key_path):
            print(f"SSH key file not found at {self.ssh_key_path}")

            print("Generating new SSH key...")
            ssh_keys = utils.generate_ssh_key_pair()
            self.ssh_key = ssh_keys["public"]
            self.private_key = ssh_keys["private"]

        try:
            with open(self.ssh_key_path, "r") as ssh_key_file:
                self.ssh_key = ssh_key_file.read().strip()

            os.environ["OPAL_POLICY_REPO_SSH_KEY"] = self.ssh_key
        except Exception as e:
            print(f"Error loading SSH key: {e}")

    def set_envvars(self):
        # Update .env file
        with open(".env", "a") as env_file:
            env_file.write(f'OPAL_POLICY_REPO_URL="{self.get_repo_url()}"\n')
            env_file.write(f'OPAL_POLICY_REPO_BRANCH="{self.test_branch}"\n')

        with open(".env", "a") as env_file:
            env_file.write(f'OPAL_POLICY_REPO_SSH_KEY="{self.ssh_key}"\n')

    def get_repo_url(self):
        if self.owner is None:
            raise Exception("Owner not set")

        if self.portocol == "ssh":
            return f"git@{self.host}:{self.owner}/{self.repo}.git"

        if self.protocol == "https":
            if self.github_pat:
                return f"https://{self.owner}:{self.github_pat}@{self.host}/{self.owner}/{self.repo}.git"

        if self.password is None:
            raise Exception("Password not set")

        return f"https://{self.owner}:{self.password}@{self.host}:{self.port}/{self.owner}/{self.repo}.git"

    def get_source_repo_url(self):
        return f"git@{self.host}:{self.source_repo_owner}/{self.source_repo_name}.git"

    def clone_initial_repo(self):
        Repo.clone_from(self.get_source_repo_url(), self.local_repo_path)

    def check_repo_exists(self):
        try:
            gh = Github(self.ssh_key)
            repo_list = gh.get_repos()
            for repo in repo_list:
                if repo.full_name == self.repo_name:
                    print(f"Repository {self.repo_name} already exists.")
                    return True

        except Exception as e:
            print(f"Error checking repository existence: {e}")

        return False

    def create_target_repo(self):
        if self.check_repo_exists():
            return

        try:
            gh = Github(self.ssh_key)
            gh.get_user().create_repo(self.repo)
            print(f"Repository {self.repo} created successfully.")
        except Exception as e:
            print(f"Error creating repository: {e}")

    def fork_target_repo(self):
        if self.check_repo_exists():
            return

        print(f"Forking repository {self.source_repo_name}...")

        if self.github_pat is None:
            try:
                gh = Github(self.ssh_key)
                gh.get_user().create_fork(self.source_repo_owner, self.source_repo_name)
                print(f"Repository {self.source_repo_name} forked successfully.")
            except Exception as e:
                print(f"Error forking repository: {e}")
            return

        # Try with PAT
        try:
            headers = {"Authorization": f"token {self.github_pat}"}
            response = requests.post(
                f"https://api.github.com/repos/{self.source_repo_owner}/{self.source_repo_name}/forks",
                headers=headers,
            )
            if response.status_code == 202:
                print("Fork created successfully!")
            else:
                print(f"Error creating fork: {response.status_code}")
                print(response.json())

        except Exception as e:
            print(f"Error forking repository: {str(e)}")

    def cleanup(self):
        self.delete_test_branches()

    def delete_test_branches(self):
        """Deletes all branches starting with 'test-' from the specified
        repository."""

        try:
            print(f"Deleting test branches from {self.repo_name}...")

            # Initialize Github API
            gh = Github(self.ssh_key)

            # Get the repository
            repo = gh.get_repo(self.repo_name)

            # Enumerate branches and delete pytest- branches
            branches = repo.get_branches()
            for branch in branches:
                if branch.name.startswith("test-"):
                    ref = f"heads/{branch.name}"
                    repo.get_git_ref(ref).delete()
                    print(f"Deleted branch: {branch.name}")
                else:
                    print(f"Skipping branch: {branch.name}")

            print("All test branches have been deleted successfully.")
        except Exception as e:
            print(f"An error occurred: {e}")

        return

    def generate_test_branch(self):
        self.test_branch = (
            f"test-{random.randint(1000, 9999)}{random.randint(1000, 9999)}"
        )
        os.environ["OPAL_POLICY_REPO_BRANCH"] = self.test_branch

    def create_test_branch(self):
        try:
            os.chdir(self.local_repo_path)
            subprocess.run(["git", "checkout", "-b", self.test_branch], check=True)
            subprocess.run(
                ["git", "push", "--set-upstream", "origin", self.test_branch],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Git command failed: {e}")

    def prepare_policy_repo(self):
        # Remove any existing repo directory
        subprocess.run(["rm", "-rf", "./opal-example-policy-repo"], check=True)

        self.clone_initial_repo()

        if self.should_fork:
            self.fork_target_repo()
        else:
            self.create_target_repo()

        self.generate_test_branch()
        self.create_test_branch()

    def add_ssh_key(self):
        gh = Github(self.ssh_key)
        user = gh.get_user()
        keys = user.get_keys()
        for key in keys:
            if key.title == "OPAL":
                return

        key = user.create_key("OPAL", self.ssh_key)
        print(f"SSH key added: {key.title}")

    def create_webhook(self):
        gh = Github(self.ssh_key)
        repo = gh.get_repo(self.repo_name)
        repo.create_hook(
            "web",
            {
                "url": f"http://{self.webhook_host}:{self.webhook_port}/webhook",
                "content_type": "json",
                f"secret": {self.webhook_secret},
                "insecure_ssl": "1",
            },
            events=["push"],
            active=True,
        )
        print("Webhook created successfully.")

    def clone_and_update(
        self,
        branch,
        file_name,
        file_content,
        CLONE_DIR,
        authenticated_url,
        COMMIT_MESSAGE,
    ):
        """Clone the repository, update the specified branch, and push
        changes."""
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
            repo.git.push("origin", branch)

        # Clean up the cloned repository
        print(f"Cleaning up branch {branch}...")
        shutil.rmtree(CLONE_DIR)

        print(f"Branch {branch} processed successfully.")

    def update_branch(self, branch, file_name, file_content):
        temp_dir = self.settings.temp_dir

        self.logger.info(
            f"Updating branch '{branch}' with file '{file_name}' content..."
        )

        # Decode escape sequences in the file content
        file_content = codecs.decode(file_content, "unicode_escape")

        GITHUB_REPO_URL = (
            f"https://github.com/{self.settings.username}/{self.settings.repo_name}.git"
        )
        username = self.settings.username
        PASSWORD = self.settings.password
        CLONE_DIR = os.path.join(temp_dir, "branch_update")
        COMMIT_MESSAGE = "Automated update commit"

        # Append credentials to the repository URL
        authenticated_url = GITHUB_REPO_URL.replace(
            "https://", f"https://{username}:{PASSWORD}@"
        )

        try:
            self.clone_and_update(
                branch,
                file_name,
                file_content,
                CLONE_DIR,
                authenticated_url,
                COMMIT_MESSAGE,
            )
        except Exception as e:
            self.logger.error(f"Error updating branch: {e}")
            return False
        return True
