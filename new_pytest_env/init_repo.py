import requests
from git import Repo
import os
import shutil

# Replace these with your Gitea server details and personal access token
GITEA_BASE_URL = "http://localhost:3000/api/v1"  # Replace with your Gitea server URL
with open("./gitea_access_token.tkn") as gitea_access_token_file:
    ACCESS_TOKEN = gitea_access_token_file.read().strip()  # Read and strip token
USERNAME = "permitAdmin2"  # Your Gitea username

def repo_exists(repo_name):
    url = f"{GITEA_BASE_URL}/repos/{USERNAME}/{repo_name}"
    headers = {"Authorization": f"token {ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print(f"Repository '{repo_name}' already exists.")
        return True
    elif response.status_code == 404:
        return False
    else:
        print(f"Failed to check repository: {response.status_code} {response.text}")
        response.raise_for_status()

def create_gitea_repo(repo_name, description="", private=False, auto_init=True):
    url = f"{GITEA_BASE_URL}/user/repos"
    headers = {
        "Authorization": f"token {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": repo_name,
        "description": description,
        "private": private,
        "auto_init": auto_init
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        print("Repository created successfully!")
        return response.json()
    else:
        print(f"Failed to create repository: {response.status_code} {response.text}")
        response.raise_for_status()

def clone_repo_with_gitpython(repo_name, clone_directory):
    repo_url = f"http://localhost:3000/{USERNAME}/{repo_name}.git"
    if ACCESS_TOKEN:
        repo_url = f"http://{USERNAME}:{ACCESS_TOKEN}@localhost:3000/{USERNAME}/{repo_name}.git"
    try:
        if os.path.exists(clone_directory):
            print(f"Directory '{clone_directory}' already exists. Deleting it...")
            shutil.rmtree(clone_directory)
        Repo.clone_from(repo_url, clone_directory)
        print(f"Repository '{repo_name}' cloned successfully into '{clone_directory}'.")
    except Exception as e:
        print(f"Failed to clone repository '{repo_name}': {e}")

def reset_repo_with_rbac(repo_directory, source_rbac_file):
    try:
        if not os.path.exists(repo_directory):
            raise FileNotFoundError(f"Repository directory '{repo_directory}' does not exist.")
        git_dir = os.path.join(repo_directory, ".git")
        if not os.path.exists(git_dir):
            raise FileNotFoundError(f"The directory '{repo_directory}' is not a valid Git repository (missing .git folder).")
        for item in os.listdir(repo_directory):
            item_path = os.path.join(repo_directory, item)
            if os.path.basename(item_path) == ".git":
                continue
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        destination_rbac_path = os.path.join(repo_directory, "rbac.rego")
        shutil.copy2(source_rbac_file, destination_rbac_path)
        repo = Repo(repo_directory)
        repo.git.add(all=True)
        repo.index.commit("Reset repository to only include 'rbac.rego'")
        print(f"Repository reset successfully. 'rbac.rego' is the only file and changes are committed.")
    except Exception as e:
        print(f"Error resetting repository: {e}")

def push_repo_to_remote(repo_directory):
    try:
        repo = Repo(repo_directory)
        if "origin" not in [remote.name for remote in repo.remotes]:
            raise ValueError("No remote named 'origin' found in the repository.")
        repo.remotes.origin.push()
        print("Changes pushed to remote repository successfully.")
    except Exception as e:
        print(f"Error pushing changes to remote: {e}")

def cleanup_local_repo(repo_directory):
    """
    Remove the local repository directory.

    :param repo_directory: Directory of the cloned repository
    """
    try:
        if os.path.exists(repo_directory):
            shutil.rmtree(repo_directory)
            print(f"Local repository '{repo_directory}' has been cleaned up.")
        else:
            print(f"Local repository '{repo_directory}' does not exist. No cleanup needed.")
    except Exception as e:
        print(f"Error during cleanup: {e}")

# Example usage
repo_name = "test-repo"
description = "This is a test repository created via API."
private = False
clone_directory = "./test-repo"
source_rbac_file = "./new_pytest_env/rbac.rego"

try:
    if not repo_exists(repo_name):
        create_gitea_repo(repo_name, description, private)
    clone_repo_with_gitpython(repo_name, clone_directory)
    reset_repo_with_rbac(clone_directory, source_rbac_file)
    push_repo_to_remote(clone_directory)
    cleanup_local_repo(clone_directory)
except Exception as e:
    print("Error:", e)
