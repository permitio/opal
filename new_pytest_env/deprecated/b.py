def clone_repo(repo_url, destination_path):
    """
    Clone a repository from a given URL to the destination path.
    If the destination path exists, it will be removed first.
    """
    if os.path.exists(destination_path):
        print(f"(git) Folder {destination_path} already exists. Deleting it...")
        shutil.rmtree(destination_path)
    try:
        Repo.clone_from(repo_url, destination_path)
        print(f"(git) Repository cloned successfully to {destination_path}")
    except Exception as e:
        print(f"(git) An error occurred while cloning: {e}")

def create_gitea_repo(base_url, api_token, repo_name, user_name):
    """
    Create a repository in Gitea.
    If the repository already exists, return its URL.
    """
    headers = {
        "Authorization": f"token {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "Python-Gitea-Script"
    }

    if user_name:  # Create repo for specific user
        url = f"{base_url}/api/v1/{user_name}/repos"
    else:  # Create repo for authenticated user
        url = f"{base_url}/api/v1/user/repos"

    data = {"name": repo_name, "private": False}

    response = requests.get(url, json=data, headers=headers)
    
    if response.status_code == 201:
        repo_data = response.json()
        print(f"(git) Repository created: {repo_data['html_url']}")
        return repo_data['clone_url']
    elif response.status_code == 409:  # Repo already exists
        print(f"(git) Repository '{repo_name}' already exists in Gitea.")
        return f"{base_url}/{user_name}/{repo_name}.git" if user_name else f"{base_url}/user/{repo_name}.git"
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
            print(f"(git) Branch '{branch_name}' created from '{base_branch}'.")
        else:
            print(f"(git) Branch '{branch_name}' already exists.")

        # Checkout the new branch
        repo.git.checkout(branch_name)
        print(f"(git) Switched to branch '{branch_name}'.")
    except Exception as e:
        print(f"(git) An error occurred while creating the branch: {e}")

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
            print(f"(git) Remote '{remote_name}' added with URL: {auth_repo_url}")
        else:
            print(f"(git) Remote '{remote_name}' already exists.")

        # Push all branches to the remote
        remote = repo.remotes[remote_name]
        remote.push(refspec="refs/heads/*:refs/heads/*")
        print(f"(git) All branches pushed to {auth_repo_url}")

        # Push all tags to the remote
        remote.push(tags=True)
        print(f"(git) All tags pushed to {auth_repo_url}")

    except Exception as e:
        print(f"(git) An error occurred while pushing: {e}")

def check_gitea_repo_exists(gitea_url: str, owner: str, repo_name: str, token: str = None) -> bool:
    """
    Check if a Gitea repository exists.

    Args:
        gitea_url (str): Base URL of the Gitea instance (e.g., 'https://gitea.example.com').
        owner (str): Owner of the repository (user or organization).
        repo_name (str): Name of the repository.
        token (str): Optional Personal Access Token for authentication.

    Returns:
        bool: True if the repository exists, False otherwise.
    """
    # Construct the API URL
    api_url = f"{gitea_url}/api/v1/repos/{owner}/{repo_name}"

    # Set headers for authentication if token is provided
    headers = {"Authorization": f"token {token}"} if token else {}

    try:
        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            return True  # Repository exists
        elif response.status_code == 404:
            return False  # Repository does not exist
        else:
            print(f"Unexpected response: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Gitea: {e}")
        return False

def get_highest_branch_number(gitea_repo_url: str, api_token: str):
    """
    Retrieve the highest numbered branch in the Gitea repository.
    """
    try:
        url = f"{gitea_repo_url}/branches"
        headers = {"Authorization": f"token {api_token}"}

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(f"Failed to fetch branches: {response.json()}")

        branches = response.json()
        max_number = 0
        for branch in branches:
            branch_name = branch["name"]
            if branch_name.startswith("test_"):
                try:
                    branch_number = int(branch_name.split("_")[1])
                    max_number = max(max_number, branch_number)
                except ValueError:
                    continue  # Ignore branches with invalid number format

        return max_number
    except Exception as e:
        print(f"(git) Error retrieving branches: {e}")
        return 0

def manage_iteration_number(env_var_name, gitea_repo_url, api_token):
    """
    Manage the iteration number stored in an environment variable.
    Ensure it's higher than any branch number in the Gitea repository.
    """
    # Get the iteration number from the environment variable or initialize it
    iteration_number = int(os.getenv(env_var_name, 0))

    # Ensure iteration_number is higher than the highest branch number in Gitea
    if check_gitea_repo_exists(gitea_base_url, user_name, repo_name, gitea_api_token):
        highest_branch_number = get_highest_branch_number(gitea_repo_url, api_token)
        iteration_number = max(iteration_number, highest_branch_number + 1)

    # Update the environment variable
    os.environ[env_var_name] = str(iteration_number)
    return iteration_number

def clone_github_to_gitea(_env_var_name, _gitea_repo_url, _gitea_api_token, _destination_path, _repo_url, _gitea_base_url, _repo_name, _gitea_username, _gitea_password):
    # Step 1: Manage iteration number
    iteration_number = manage_iteration_number(_env_var_name, _gitea_repo_url, _gitea_api_token)
    branch_name = f"test_{iteration_number}"

    # Step 2: Clone the repository from GitHub
    clone_repo(_repo_url, _destination_path)

    # Step 3: Check if the repository exists in Gitea, create it if not
    try:
        create_gitea_repo(_gitea_base_url, _gitea_api_token, _repo_name, user_name)
    except Exception as e:
        print(f"(git) Error while creating Gitea repository: {e}")

    # Step 4: Create a new branch in the local repository
    create_branch(_destination_path, branch_name)

    # Step 5: Push the repository to Gitea, including all branches
    push_to_gitea_with_credentials(_destination_path, f"{_gitea_base_url}/{_gitea_username}/{_repo_name}.git", _gitea_username, _gitea_password)

    # Increment the iteration number for the next run
    iteration_number += 1
    os.environ[_env_var_name] = str(iteration_number)

    # Return the link to the Gitea repository with the specific branch
    branch_url = f"{_gitea_base_url}/{_gitea_username}/{_repo_name}/src/branch/{branch_name}"
    print(f"(git) Repository and branch created: {branch_url}")
    return branch_url
