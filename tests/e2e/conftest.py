"""
PyTest configuration and fixtures for OPAL E2E tests.

This module provides reusable fixtures for setting up and tearing down
the OPAL testing environment including Docker containers, authentication,
and policy repositories.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Generator

import pytest
import requests


@pytest.fixture(scope="session")
def script_dir() -> Path:
    """Return the directory containing the test scripts."""
    return Path(__file__).parent.parent.parent / "app-tests"


@pytest.fixture(scope="session")
def opal_keys() -> Generator[Dict[str, str], None, None]:
    """
    Generate OPAL authentication keys and tokens.
    
    Yields:
        Dictionary containing authentication keys and tokens
    """
    print("\n- Generating OPAL keys")
    
    # Generate passphrase and SSH keys
    passphrase = "123456"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "rsa", "-b", "4096", "-m", "pem", 
         "-f", "opal_crypto_key", "-N", passphrase],
        check=True
    )
    
    # Read keys
    with open("opal_crypto_key.pub", "r") as f:
        public_key = f.read().strip()
    
    with open("opal_crypto_key", "r") as f:
        private_key = f.read().replace("\n", "_")
    
    # Clean up key files
    os.remove("opal_crypto_key.pub")
    os.remove("opal_crypto_key")
    
    # Generate master token
    master_token = subprocess.check_output(
        ["openssl", "rand", "-hex", "16"]
    ).decode().strip()
    
    # Start temporary OPAL server for token generation
    print("    Starting OPAL server for keygen")
    subprocess.run(
        ["docker", "rm", "-f", "--wait", "opal-server-keygen"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    env_vars = [
        "-e", f"OPAL_AUTH_PUBLIC_KEY={public_key}",
        "-e", f"OPAL_AUTH_PRIVATE_KEY={private_key}",
        "-e", f"OPAL_AUTH_PRIVATE_KEY_PASSPHRASE={passphrase}",
        "-e", f"OPAL_AUTH_MASTER_TOKEN={master_token}",
        "-e", "OPAL_AUTH_JWT_AUDIENCE=https://api.opal.ac/v1/",
        "-e", "OPAL_AUTH_JWT_ISSUER=https://opal.ac/",
        "-e", "OPAL_REPO_WATCHER_ENABLED=0",
        "-p", "7002:7002"
    ]
    
    subprocess.run(
        ["docker", "run", "--rm", "-d", "--name", "opal-server-keygen"] + 
        env_vars + 
        ["permitio/opal-server:latest"],
        check=True
    )
    
    time.sleep(2)
    
    # Wait for server to be ready
    print("    Waiting for OPAL server to be ready...")
    timeout = 30
    for _ in range(timeout):
        try:
            response = requests.get("http://localhost:7002/", timeout=3)
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        raise TimeoutError("OPAL server failed to start")
    
    # Obtain client token
    print("    Obtaining tokens")
    client_response = requests.post(
        "http://localhost:7002/token",
        headers={
            "Authorization": f"Bearer {master_token}",
            "Content-Type": "application/json"
        },
        json={"type": "client"},
        timeout=5
    )
    client_response.raise_for_status()
    client_token = client_response.json()["token"]
    
    # Obtain datasource token
    datasource_response = requests.post(
        "http://localhost:7002/token",
        headers={
            "Authorization": f"Bearer {master_token}",
            "Content-Type": "application/json"
        },
        json={"type": "datasource"},
        timeout=5
    )
    datasource_response.raise_for_status()
    datasource_token = datasource_response.json()["token"]
    
    # Stop temporary server
    print("    Stopping OPAL server for keygen")
    subprocess.run(
        ["docker", "stop", "opal-server-keygen"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    subprocess.run(
        ["docker", "rm", "opal-server-keygen"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    time.sleep(5)
    
    keys = {
        "public_key": public_key,
        "private_key": private_key,
        "passphrase": passphrase,
        "master_token": master_token,
        "client_token": client_token,
        "datasource_token": datasource_token
    }
    
    yield keys


@pytest.fixture(scope="session")
def policy_repo(script_dir: Path, opal_keys: Dict[str, str]) -> Generator[Dict[str, str], None, None]:
    """
    Set up a local Gitea server and policy repository.
    
    Args:
        script_dir: Path to the script directory
        opal_keys: Authentication keys and tokens
        
    Yields:
        Dictionary containing repository URLs and branch name
    """
    print("\n- Preparing policy repository")
    
    # Start Gitea
    compose_file = script_dir / "docker-compose-app-tests.yml"
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d", "gitea", "--force-recreate"],
        check=True,
        cwd=script_dir
    )
    time.sleep(5)
    
    # Wait for Gitea to be ready
    print("  Waiting for Gitea to be ready...")
    timeout = 120
    for _ in range(timeout):
        try:
            response = requests.get("http://localhost:3000", timeout=3)
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        raise TimeoutError("Gitea failed to start")
    
    # Wait for Gitea API
    for _ in range(timeout):
        try:
            response = requests.get("http://localhost:3000/api/v1/version", timeout=3)
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(2)
    else:
        raise TimeoutError("Gitea API failed to initialize")
    
    print("  Gitea is ready!")
    
    # Create admin user
    print("  Creating initial admin user...")
    subprocess.run(
        ["docker", "exec", "gitea", "gitea", "admin", "user", "create",
         "--username", "gitea_admin",
         "--password", "admin123",
         "--email", "admin@gitea.local",
         "--admin",
         "--must-change-password=false"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Prepare local repository
    temp_repo = script_dir / "temp-repo"
    if temp_repo.exists():
        subprocess.run(["rm", "-rf", str(temp_repo)], check=True)
    
    temp_repo.mkdir(parents=True)
    
    print(f"  Creating temp repo for policy repository at {temp_repo}...")
    subprocess.run(["git", "init"], cwd=temp_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@opal.local"], cwd=temp_repo, check=True)
    subprocess.run(["git", "config", "user.name", "OPAL Test"], cwd=temp_repo, check=True)
    
    # Copy policy files
    print("  Copying policy files...")
    policy_source = script_dir / "opal-tests-policy-repo-main"
    subprocess.run(
        ["cp", "-r", f"{policy_source}/.", str(temp_repo)],
        check=True
    )
    
    # Create initial commit
    subprocess.run(["git", "add", "."], cwd=temp_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial policies from opal-tests-policy-repo"],
        cwd=temp_repo,
        check=True
    )
    
    # Set up repository URLs
    repo_url = "http://gitea_admin:admin123@localhost:3000/gitea_admin/policy-repo.git"
    repo_url_webhook = "http://gitea:3000/gitea_admin/policy-repo.git"
    
    subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=temp_repo, check=True)
    
    # Delete existing repository if it exists
    print("  Checking if repository exists...")
    try:
        requests.get("http://localhost:3000/api/v1/repos/gitea_admin/policy-repo", timeout=3)
        print("  Repository already exists, deleting it...")
        requests.delete(
            "http://localhost:3000/api/v1/repos/gitea_admin/policy-repo",
            auth=("gitea_admin", "admin123"),
            timeout=3
        )
        time.sleep(2)
    except requests.RequestException:
        pass
    
    # Create repository via API
    print("  Creating repository via API...")
    response = requests.post(
        "http://localhost:3000/api/v1/user/repos",
        auth=("gitea_admin", "admin123"),
        headers={"Content-Type": "application/json"},
        json={"name": "policy-repo", "private": False, "auto_init": False},
        timeout=5
    )
    
    # Push to repository
    print("  Pushing to repository...")
    try:
        subprocess.run(["git", "push", "-u", "origin", "master:main"], cwd=temp_repo, check=True)
    except subprocess.CalledProcessError:
        subprocess.run(["git", "push", "-u", "origin", "master"], cwd=temp_repo, check=True)
    
    # Create and push test branch
    import random
    branch_name = f"test-{random.randint(10000000, 99999999)}"
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=temp_repo, check=True)
    subprocess.run(["git", "push", "-u", "origin", branch_name], cwd=temp_repo, check=True)
    
    # Clone fresh for testing
    test_repo = script_dir / "opal-tests-policy-repo"
    if test_repo.exists():
        subprocess.run(["rm", "-rf", str(test_repo)], check=True)
    
    subprocess.run(["git", "clone", repo_url, str(test_repo)], cwd=script_dir, check=True)
    subprocess.run(["git", "checkout", branch_name], cwd=test_repo, check=True)
    
    repo_info = {
        "url": repo_url,
        "webhook_url": repo_url_webhook,
        "branch": branch_name,
        "path": str(test_repo)
    }
    
    yield repo_info
    
    # Cleanup
    if temp_repo.exists():
        subprocess.run(["rm", "-rf", str(temp_repo)])
    if test_repo.exists():
        subprocess.run(["rm", "-rf", str(test_repo)])


@pytest.fixture(scope="session")
def opal_environment(
    script_dir: Path,
    opal_keys: Dict[str, str],
    policy_repo: Dict[str, str]
) -> Generator[None, None, None]:
    """
    Set up the complete OPAL environment with server and client containers.
    
    Args:
        script_dir: Path to the script directory
        opal_keys: Authentication keys and tokens
        policy_repo: Policy repository information
    """
    print("\n- Starting OPAL environment")
    
    # Create .env file
    env_file = script_dir / ".env"
    with open(env_file, "w") as f:
        f.write(f'OPAL_AUTH_PUBLIC_KEY="{opal_keys["public_key"]}"\n')
        f.write(f'OPAL_AUTH_PRIVATE_KEY="{opal_keys["private_key"]}"\n')
        f.write(f'OPAL_AUTH_MASTER_TOKEN="{opal_keys["master_token"]}"\n')
        f.write(f'OPAL_CLIENT_TOKEN="{opal_keys["client_token"]}"\n')
        f.write(f'OPAL_AUTH_PRIVATE_KEY_PASSPHRASE="{opal_keys["passphrase"]}"\n')
        f.write(f'OPAL_POLICY_REPO_URL="{policy_repo["url"]}"\n')
        f.write(f'OPAL_POLICY_REPO_URL_FOR_WEBHOOK="{policy_repo["webhook_url"]}"\n')
        f.write(f'POLICY_REPO_BRANCH="{policy_repo["branch"]}"\n')
    
    # Start OPAL services
    compose_file = script_dir / "docker-compose-app-tests.yml"
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), 
         "up", "-d", "--force-recreate"],
        check=True,
        cwd=script_dir
    )
    
    print("  Waiting for OPAL services to start...")
    time.sleep(15)
    
    yield
    
    # Cleanup
    print("\n- Cleaning up OPAL environment")
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "down"],
        cwd=script_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    if env_file.exists():
        env_file.unlink()
    
    # Clean up data directories
    for dir_name in ["gitea-data", "git-repos"]:
        dir_path = script_dir / dir_name
        if dir_path.exists():
            subprocess.run(["rm", "-rf", str(dir_path)])


@pytest.fixture
def compose_command(script_dir: Path):
    """
    Provide a helper function to run docker-compose commands.
    
    Args:
        script_dir: Path to the script directory
        
    Returns:
        Function to execute docker-compose commands
    """
    def run_compose(*args):
        compose_file = script_dir / "docker-compose-app-tests.yml"
        env_file = script_dir / ".env"
        cmd = ["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file)] + list(args)
        return subprocess.run(cmd, cwd=script_dir, capture_output=True, text=True)
    
    return run_compose
