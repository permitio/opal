import codecs

from tests.policy_repos.policy_repo_base import PolicyRepoBase


class GitlabPolicyRepo(PolicyRepoBase):
    def __init__(self, owner, repo, token):
        self.owner = owner
        self.repo = repo
        self.token = token

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

        self.logger.debug(
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

    # implementation using git subprocess
    # try:
    #     # Change to the policy repository directory
    #     os.chdir(opal_repo_path)

    #     # Create a .rego file with the policy name as the package
    #     with open(regofile, "w") as f:
    #         f.write(f"package {policy_name}\n")

    #     # Run Git commands to add, commit, and push the policy file
    #     subprocess.run(["git", "add", regofile], check=True)
    #     subprocess.run(["git", "commit", "-m", f"Add {regofile}"], check=True)
    #     subprocess.run(["git", "push"], check=True)
    # finally:
    #     # Change back to the previous directory
    #     os.chdir("..")
