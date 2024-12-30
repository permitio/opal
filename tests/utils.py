import json
import time
import os
import random
import shutil
import subprocess
import tempfile
import requests
import sys
import docker
import subprocess
import platform
from tests.containers.opal_server_container  import OpalServerContainer
from git import Repo
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

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

current_folder = os.path.dirname(os.path.abspath(__file__))

def generate_ssh_key():
    # Generate a private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,  # Standard public exponent
        key_size=2048,          # Key size in bits
    )
    
    # Serialize the private key in PEM format
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),  # No passphrase
    )
    
    # Generate the corresponding public key
    public_key = private_key.public_key()
    
    # Serialize the public key in OpenSSH format
    public_key_openssh = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    
    # Return the keys as strings
    return private_key_pem.decode('utf-8'), public_key_openssh.decode('utf-8')

async def opal_authorize(user: str, policy_url: str):
    """Test if the user is authorized based on the current policy."""

    
    # HTTP headers and request payload
    headers = {"Content-Type": "application/json" }
    data = {
        "input": {
            "user": user,
            "action": "read",
            "object": "id123",
            "type": "finance"
        }
    }

    # Send POST request to OPA
    response = requests.post(policy_url, headers=headers, json=data)

    allowed = False
    # Parse the JSON response
    assert "result" in response.json()
    allowed = response.json()["result"]
    print(f"Authorization test result: {user} is {'ALLOWED' if allowed else 'NOT ALLOWED'}.")
    
    return allowed

def wait_policy_repo_polling_interval(opal_server_container: OpalServerContainer):
    # Allow time for the update to propagate
    for i in range(int(opal_server_container.settings.polling_interval), 0, -1):
        print(f"waiting for OPAL server to pull the new policy {i} secondes left", end='\r') 
        time.sleep(1)

def is_port_available(port):
    # Determine the platform (Linux or macOS)
    system_platform = platform.system().lower()
    
    # Run the appropriate netstat command based on the platform
    if system_platform == 'darwin':  # macOS
        result = subprocess.run(['netstat', '-an'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # macOS 'netstat' shows *.<port> format for listening ports
        if f'.{port} ' in result.stdout:
            return False  # Port is in use
    else:  # Linux
        result = subprocess.run(['netstat', '-an'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Linux 'netstat' shows 0.0.0.0:<port> or :::<port> format for listening ports
        if f':{port} ' in result.stdout or f'::{port} ' in result.stdout:
            return False  # Port is in use
    
    return True  # Port is available

def find_available_port(starting_port=5001):
    port = starting_port
    while True:
        if is_port_available(port):
            return port
        port += 1

def get_client_and_server_count(json_data):
    """
    Extracts the client_count and server_count from a given JSON string.

    Args:
        json_data (str): A JSON string containing the client and server counts.

    Returns:
        dict: A dictionary with keys 'client_count' and 'server_count'.
    """
    try:
        # Parse the JSON string
        data = json.loads(json_data)
        
        # Extract client and server counts
        client_count = data.get("client_count", 0)
        server_count = data.get("server_count", 0)
        
        return {"client_count": client_count, "server_count": server_count}
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON input.")
