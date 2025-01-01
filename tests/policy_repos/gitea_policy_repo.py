import codecs
import os

from git import GitCommandError, Repo

from tests.containers.settings.gitea_settings import GiteaSettings
from tests.policy_repos.policy_repo_base import PolicyRepoBase


class GiteaPolicyRepo(PolicyRepoBase):
    def __init__(self):
        super().__init__()

    def setup(self, gitea_settings: GiteaSettings):
        self.settings = gitea_settings

    def get_repo_url(self):
        if self.settings is None:
            raise Exception("Gitea settings not set")

        return f"http://{self.settings.container_name}:{self.settings.port_http}/{self.settings.username}/{self.settings.repo_name}.git"

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

        # Push changes to the remote repository
        print(f"Pushing changes for branch {branch}...")
        try:
            repo.git.push(authenticated_url, branch)
        except GitCommandError as e:
            print(f"Error pushing branch {branch}: {e}")

    def update_branch(self, branch, file_name, file_content):
        temp_dir = self.settings.temp_dir

        self.logger.info(
            f"Updating branch '{branch}' with file '{file_name}' content..."
        )

        # Decode escape sequences in the file content
        file_content = codecs.decode(file_content, "unicode_escape")

        GITEA_REPO_URL = f"http://localhost:{self.settings.port_http}/{self.settings.username}/{self.settings.repo_name}.git"
        username = self.settings.username
        PASSWORD = self.settings.password
        CLONE_DIR = os.path.join(temp_dir, "branch_update")
        COMMIT_MESSAGE = "Automated update commit"

        # Append credentials to the repository URL
        authenticated_url = GITEA_REPO_URL.replace(
            "http://", f"http://{username}:{PASSWORD}@"
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
            print("Operation completed successfully.")
        finally:
            # Ensure cleanup is performed regardless of success or failure
            self.cleanup(CLONE_DIR)
