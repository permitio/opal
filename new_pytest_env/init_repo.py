import requests
from git import Repo
import os

# Replace these with your Gitea server details and personal access token
GITEA_BASE_URL = "http://localhost:3000/api/v1"  # Replace with your Gitea server URL
with open("./gitea_access_token.tkn") as gitea_access_token_file:
    ACCESS_TOKEN = gitea_access_token_file.read().strip()  # Read and strip token
USERNAME = "ariAdmin2"  # Your Gitea username

def repo_exists(repo_name):
    """
    Check if a repository exists in Gitea for the user.

    :param repo_name: Name of the repository to check
    :return: True if the repository exists, False otherwise
    """
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
    """
    Create a repository in Gitea using the API.

    :param repo_name: Name of the repository
    :param description: Description of the repository
    :param private: Boolean indicating if the repository should be private
    :param auto_init: Boolean to auto-initialize with a README
    :return: Response JSON from the API
    """
    # API endpoint for creating a repository
    url = f"{GITEA_BASE_URL}/user/repos"

    # Headers for authentication
    headers = {
        "Authorization": f"token {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # Repository data
    payload = {
        "name": repo_name,
        "description": description,
        "private": private,
        "auto_init": auto_init
    }

    # Make the POST request
    response = requests.post(url, json=payload, headers=headers)

    # Check response status
    if response.status_code == 201:
        print("Repository created successfully!")
        return response.json()
    else:
        print(f"Failed to create repository: {response.status_code} {response.text}")
        response.raise_for_status()

def clone_repo_with_gitpython(repo_name, clone_directory):
    """
    Clone a Gitea repository using GitPython.

    :param repo_name: Name of the repository to clone
    :param clone_directory: Directory where the repository will be cloned
    """
    repo_url = f"http://localhost:3000/{USERNAME}/{repo_name}.git"

    # If the repository is private, include authentication in the URL
    if ACCESS_TOKEN:
        repo_url = f"http://{USERNAME}:{ACCESS_TOKEN}@localhost:3000/{USERNAME}/{repo_name}.git"

    try:
        # Ensure the directory does not already exist
        if os.path.exists(clone_directory):
            print(f"Directory '{clone_directory}' already exists. Skipping clone.")
            return

        # Clone the repository
        Repo.clone_from(repo_url, clone_directory)
        print(f"Repository '{repo_name}' cloned successfully into '{clone_directory}'.")
    except Exception as e:
        print(f"Failed to clone repository '{repo_name}': {e}")

# Example usage
repo_name = "test-repo"
description = "This is a test repository created via API."
private = False
clone_directory = "./test-repo"  # Directory where the repository will be cloned

try:
    # Check if the repository already exists
    if repo_exists(repo_name):
        print(f"Repository '{repo_name}' already exists.")
    else:
        # Create the repository if it doesn't exist
        create_gitea_repo(repo_name, description, private)

    # Clone the repository
    clone_repo_with_gitpython(repo_name, clone_directory)

except Exception as e:
    print("Error:", e)
