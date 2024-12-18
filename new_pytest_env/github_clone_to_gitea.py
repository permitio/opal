import os
import shutil
from git import Repo
import requests

def clone_repo(repo_url, destination_path):
    """
    Clone a repository from a given URL to the destination path.
    If the destination path exists, it will be removed first.
    """
    if os.path.exists(destination_path):
        print(f"Folder {destination_path} already exists. Deleting it...")
        shutil.rmtree(destination_path)

    try:
        Repo.clone_from(repo_url, destination_path)
        print(f"Repository cloned successfully to {destination_path}")
    except Exception as e:
        print(f"An error occurred while cloning: {e}")

def create_gitea_repo(base_url, api_token, repo_name, private=False):
    """
    Create a repository in Gitea.
    If the repository already exists, return its URL.
    """
    url = f"{base_url}/api/v1/user/repos"
    headers = {"Authorization": f"token {api_token}"}
    data = {"name": repo_name, "private": private}

    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        repo_data = response.json()
        print(f"Repository created: {repo_data['html_url']}")
        return repo_data['clone_url']
    elif response.status_code == 409:  # Repo already exists
        print(f"Repository '{repo_name}' already exists in Gitea.")
        return f"{base_url}/{repo_name}.git"
    else:
        raise Exception(f"Failed to create or fetch repository: {response.json()}")

def create_branch(repo_path, branch_name, base_branch="master"):
    """
    Create a new branch in the local repository based on a specified branch.
    """
    try:
        repo = Repo(repo_path)
        # Ensure the base branch is checked out
        repo.git.checkout(base_branch)

        # Create the new branch if it doesn't exist
        if branch_name not in repo.heads:
            new_branch = repo.create_head(branch_name, repo.heads[base_branch].commit)
            print(f"Branch '{branch_name}' created from '{base_branch}'.")
        else:
            print(f"Branch '{branch_name}' already exists.")

        # Checkout the new branch
        repo.git.checkout(branch_name)
        print(f"Switched to branch '{branch_name}'.")
    except Exception as e:
        print(f"An error occurred while creating the branch: {e}")

def push_to_gitea_with_credentials(cloned_repo_path, gitea_repo_url, username, password, remote_name="gitea"):
    """
    Push the cloned repository to a Gitea repository with credentials included.
    """
    try:
        # Embed credentials in the Gitea URL
        auth_repo_url = gitea_repo_url.replace("://", f"://{username}:{password}@")

        # Open the existing repository
        repo = Repo(cloned_repo_path)

        # Add the Gitea repository as a remote if not already added
        if remote_name not in [remote.name for remote in repo.remotes]:
            repo.create_remote(remote_name, auth_repo_url)
            print(f"Remote '{remote_name}' added with URL: {auth_repo_url}")
        else:
            print(f"Remote '{remote_name}' already exists.")

        # Push all branches to the remote
        remote = repo.remotes[remote_name]
        remote.push(refspec="refs/heads/*:refs/heads/*")
        print(f"All branches pushed to {auth_repo_url}")

        # Push all tags to the remote
        remote.push(tags=True)
        print(f"All tags pushed to {auth_repo_url}")

    except Exception as e:
        print(f"An error occurred while pushing: {e}")

if __name__ == "__main__":
    # Variables
    repo_url = "https://github.com/ariWeinberg/opal-example-policy-repo.git"
    repo_name = "opal-example-policy-repo"
    destination_path = f"./{repo_name}"

    gitea_base_url = "http://localhost:3000"
    gitea_api_token = "7585f7b0b3990fd13999d71723a3e9d0504e6c2c"
    gitea_username = "AriAdmin2"
    gitea_password = "Aw123456"
    gitea_repo_url = f"{gitea_base_url}/ariAdmin2/{repo_name}.git"

    branch_name = "test_1"

    # Step 1: Clone the repository from GitHub
    clone_repo(repo_url, destination_path)

    # Step 2: Check if the repository exists in Gitea, create it if not
    try:
        create_gitea_repo(gitea_base_url, gitea_api_token, repo_name)
    except Exception as e:
        print(f"Error while creating Gitea repository: {e}")

    # Step 3: Create a new branch in the local repository
    create_branch(destination_path, branch_name)

    # Step 4: Push the repository to Gitea, including all branches
    push_to_gitea_with_credentials(destination_path, gitea_repo_url, gitea_username, gitea_password)
