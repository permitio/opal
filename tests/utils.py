import os
import random
import subprocess
import requests
import sys
import docker
from git import Repo

def compose(*args):
    """
    Helper function to run docker compose commands with the given arguments.
    Assumes `docker-compose-app-tests.yml` is the compose file and `.env` is the environment file.
    """
    command = ["docker", "compose", "-f", "./docker-compose-app-tests.yml", "--env-file", ".env"] + list(args)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Compose command failed: {result.stderr.strip()}")
    return result.stdout


def check_clients_logged(log_message):
    """
    Checks if a given message is present in the logs of both opal_client containers.
    """
    print(f"- Looking for msg '{log_message}' in client's logs")
    
    # Check the logs of opal_client container with index 1
    logs_client_1 = compose("logs", "--index", "1", "opal_client")
    if log_message not in logs_client_1:
        raise ValueError(f"Message '{log_message}' not found in opal_client (index 1) logs.")
    
    # Check the logs of opal_client container with index 2
    logs_client_2 = compose("logs", "--index", "2", "opal_client")
    if log_message not in logs_client_2:
        raise ValueError(f"Message '{log_message}' not found in opal_client (index 2) logs.")
    
    print(f"Message '{log_message}' found in both client logs.")


def prepare_policy_repo(account_arg="-account=permitio"):
    print("- Clone tests policy repo to create test's branch")

    # Extract OPAL_TARGET_ACCOUNT from the command-line argument
    if not account_arg.startswith("-account="):
        raise ValueError("Account argument must be in the format -account=ACCOUNT_NAME")
    OPAL_TARGET_ACCOUNT = account_arg.split("=")[1]
    if not OPAL_TARGET_ACCOUNT:
        raise ValueError("Account name cannot be empty")
    
    print(f"OPAL_TARGET_ACCOUNT={OPAL_TARGET_ACCOUNT}")

    # Set or default OPAL_POLICY_REPO_URL
    OPAL_POLICY_REPO_URL = os.getenv("OPAL_POLICY_REPO_URL", "git@github.com:permitio/opal-example-policy-repo.git")
    print(f"OPAL_POLICY_REPO_URL={OPAL_POLICY_REPO_URL}")

    # Forking the policy repo
    ORIGINAL_REPO_NAME = os.path.basename(OPAL_POLICY_REPO_URL).replace(".git", "")
    NEW_REPO_NAME = ORIGINAL_REPO_NAME
    FORKED_REPO_URL = f"git@github.com:{OPAL_TARGET_ACCOUNT}/{NEW_REPO_NAME}.git"

    # Check if the forked repository already exists using GitHub CLI
    try:
        result = subprocess.run(
            ["gh", "repo", "list", OPAL_TARGET_ACCOUNT, "--json", "name", "-q", ".[].name"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if NEW_REPO_NAME in result.stdout:
            print(f"Forked repository {NEW_REPO_NAME} already exists.")
            OPAL_POLICY_REPO_URL = FORKED_REPO_URL
            print(f"Using existing forked repository: {OPAL_POLICY_REPO_URL}")

            delete_test_branches(OPAL_POLICY_REPO_URL)
        else:
            # Using GitHub API to fork the repository
            OPAL_TARGET_PAT = os.getenv("pat", "")
            headers = {"Authorization": f"token {OPAL_TARGET_PAT}"}
            response = requests.post(
                f"https://api.github.com/repos/permitio/opal-example-policy-repo/forks",
                headers=headers
            )
            if response.status_code == 202:
                print("Fork created successfully!")
            else:
                print(f"Error creating fork: {response.status_code}")
                print(response.json())
            OPAL_POLICY_REPO_URL = FORKED_REPO_URL
            print(f"Updated OPAL_POLICY_REPO_URL to {OPAL_POLICY_REPO_URL}")

    except Exception as e:
        print(f"Error checking or forking repository: {str(e)}")

    # Create a new branch
    POLICY_REPO_BRANCH = f"test-{random.randint(1000, 9999)}{random.randint(1000, 9999)}"
    os.environ["OPAL_POLICY_REPO_BRANCH"] = POLICY_REPO_BRANCH
    os.environ["OPAL_POLICY_REPO_URL"] = OPAL_POLICY_REPO_URL

    try:
        # Remove any existing repo directory
        subprocess.run(["rm", "-rf", "./opal-example-policy-repo"], check=True)

        # Clone the forked repository
        subprocess.run(["git", "clone", OPAL_POLICY_REPO_URL], check=True)

        # Create and push a new branch
        os.chdir("opal-example-policy-repo")
        subprocess.run(["git", "checkout", "-b", POLICY_REPO_BRANCH], check=True)
        subprocess.run(["git", "push", "--set-upstream", "origin", POLICY_REPO_BRANCH], check=True)
        os.chdir("..")
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e}")

    # Update .env file
    with open(".env", "a") as env_file:
        env_file.write(f"OPAL_POLICY_REPO_URL=\"{OPAL_POLICY_REPO_URL}\"\n")
        env_file.write(f"OPAL_POLICY_REPO_BRANCH=\"{POLICY_REPO_BRANCH}\"\n")

    # Set SSH key
    OPAL_POLICY_REPO_SSH_KEY_PATH = os.getenv("OPAL_POLICY_REPO_SSH_KEY_PATH", os.path.expanduser("~/.ssh/id_rsa"))
    with open(OPAL_POLICY_REPO_SSH_KEY_PATH, "r") as ssh_key_file:
        OPAL_POLICY_REPO_SSH_KEY = ssh_key_file.read().strip()
    os.environ["OPAL_POLICY_REPO_SSH_KEY"] = OPAL_POLICY_REPO_SSH_KEY

    with open(".env", "a") as env_file:
        env_file.write(f"OPAL_POLICY_REPO_SSH_KEY=\"{OPAL_POLICY_REPO_SSH_KEY}\"\n")

    print("- OPAL_POLICY_REPO_SSH_KEY set successfully")


def delete_test_branches(repo_path):
    """
    Deletes all branches starting with 'test-' from the specified repository.

    Args:
        repo_path (str): Path to the local Git repository.
    """
    try:

        print(f"Deleting test branches from {repo_path}")

        if "permitio" in repo_path:
            return
        
        from github import Github

        # Initialize Github API
        g = Github(os.getenv('OPAL_POLICY_REPO_SSH_KEY'))

        # Get the repository
        repo = g.get_repo(repo_path)    

        # Enumerate branches and delete pytest- branches
        branches = repo.get_branches()
        for branch in branches:
            if branch.name.startswith('test-'):
                ref = f"heads/{branch.name}"
                repo.get_git_ref(ref).delete()
                print(f"Deleted branch: {branch.name}")
            else:
                print(f"Skipping branch: {branch.name}")
            
        print("All test branches have been deleted successfully.")
    except Exception as e:
        print(f"An error occurred: {e}")
        
    return

def remove_pytest_opal_networks():
    """Remove all Docker networks with names starting with 'pytest_opal_'."""
    try:
        client = docker.from_env()
        networks = client.networks.list()
        
        for network in networks:
            if network.name.startswith("pytest_opal_"):
                try:
                    print(f"Removing network: {network.name}")
                    network.remove()
                except Exception as e:
                    print(f"Failed to remove network {network.name}: {e}")
        print("Cleanup complete!")
    except Exception as e:
        print(f"Error while accessing Docker: {e}")