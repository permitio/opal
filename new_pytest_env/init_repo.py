import requests

# Replace these with your Gitea server details and personal access token
GITEA_BASE_URL = "http://localhost:3000/api/v1"  # Replace with your Gitea server URL
with open("./gitea_access_token.tkn") as gitea_access_token_file:
    ACCESS_TOKEN = gitea_access_token_file.read()  # Replace with your token
USERNAME = "ariAdmin2"  # Your Gitea username

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

# Example usage
repo_name = "test-repo"
description = "This is a test repository created via API."
private = False

try:
    repo_info = create_gitea_repo(repo_name, description, private)
    print("Repository Info:", repo_info)
except Exception as e:
    print("Error:", e)
