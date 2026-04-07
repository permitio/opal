#!/usr/bin/env python3
"""
OPAL App Tests Runner

This script sets up and runs comprehensive integration tests for OPAL.
It replaces the original run.sh bash script with a cross-platform Python implementation.
"""

import os
import sys
import json
import time
import random
import subprocess
import tempfile
import shutil
import stat
import platform
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import requests

try:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    print("WARNING: cryptography library not available. Falling back to ssh-keygen.")

# Configure script directory
SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(SCRIPT_DIR)

# Environment variables
OPAL_AUTH_PUBLIC_KEY = os.environ.get("OPAL_AUTH_PUBLIC_KEY", "")
OPAL_AUTH_PRIVATE_KEY = os.environ.get("OPAL_AUTH_PRIVATE_KEY", "")
OPAL_AUTH_PRIVATE_KEY_PASSPHRASE = os.environ.get("OPAL_AUTH_PRIVATE_KEY_PASSPHRASE", "")
OPAL_AUTH_MASTER_TOKEN = os.environ.get("OPAL_AUTH_MASTER_TOKEN", "")
OPAL_CLIENT_TOKEN = os.environ.get("OPAL_CLIENT_TOKEN", "")
OPAL_DATA_SOURCE_TOKEN = os.environ.get("OPAL_DATA_SOURCE_TOKEN", "")

# Configuration
OPAL_IMAGE_TAG = os.environ.get("OPAL_IMAGE_TAG", "latest")
MAX_RETRIES = 5

# Global variables for policy repo setup
OPAL_POLICY_REPO_URL = ""
OPAL_POLICY_REPO_URL_FOR_WEBHOOK = ""
POLICY_REPO_BRANCH = ""


def run_cmd(cmd: list, check: bool = True, capture_output: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            **kwargs
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(cmd)}")
        print(f"Exit code: {e.returncode}")
        if e.stdout:
            print(f"Stdout: {e.stdout}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
        raise


def wait_for_url(url: str, timeout: int = 30, interval: int = 1) -> bool:
    """Wait for a URL to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


def remove_readonly_handler(func, path, exc_info):
    """
    Error handler for shutil.rmtree on Windows that handles read-only files.
    """
    if func in (os.unlink, os.remove, os.rmdir):
        # Make files writable and try again
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except:
            pass
    elif os.path.isdir(path):
        try:
            shutil.rmtree(path)
        except:
            pass


def safe_rmtree(path: Path, max_retries: int = 5, delay: float = 0.5):
    """
    Safely remove a directory tree on Windows, handling locked files.
    """
    if not path.exists():
        return
    
    # On Windows, handle permission errors more gracefully
    if platform.system() == "Windows":
        # Make all files writable first (collect paths first to avoid modification during iteration)
        files_to_fix = []
        dirs_to_fix = []
        
        try:
            for root, dirs, files in os.walk(path):
                for d in dirs:
                    dirs_to_fix.append(Path(root) / d)
                for f in files:
                    files_to_fix.append(Path(root) / f)
        except:
            pass
        
        # Fix permissions for all collected items
        for item_path in files_to_fix + dirs_to_fix:
            try:
                os.chmod(item_path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            except:
                pass
        
        # Try removing with error handler
        for attempt in range(max_retries):
            try:
                shutil.rmtree(path, onerror=remove_readonly_handler)
                # Verify it's actually deleted
                if not path.exists():
                    return
                # If still exists, wait and try again
                time.sleep(delay * (attempt + 1))
            except (PermissionError, OSError) as e:
                if attempt < max_retries - 1:
                    time.sleep(delay * (attempt + 1))  # Exponential backoff
                    # Try to unlock files again by fixing permissions
                    try:
                        if path.exists():
                            for root, dirs, files in os.walk(path):
                                for item in list(dirs) + list(files):
                                    item_path = Path(root) / item
                                    try:
                                        os.chmod(item_path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
                                    except:
                                        pass
                    except:
                        pass
                else:
                    # Last attempt failed, try using Windows-specific method
                    print(f"    Warning: Standard deletion failed, trying Windows rmdir command...")
                    try:
                        if path.is_dir():
                            result = subprocess.run(
                                ["cmd", "/c", "rmdir", "/s", "/q", str(path)],
                                check=False,
                                capture_output=True,
                                timeout=10
                            )
                            if not path.exists():
                                return
                    except Exception as cmd_err:
                        print(f"    Windows rmdir also failed: {cmd_err}")
                    # If all else fails, warn but don't crash
                    print(f"    Warning: Could not completely remove {path}. Some files may be locked.")
                    print(f"    You may need to manually delete this directory or close processes using it.")
                    return  # Don't raise, just return - cleanup is best-effort
    else:
        # On Unix-like systems, use standard rmtree
        shutil.rmtree(path, onerror=remove_readonly_handler)


def configure_git_identity():
    """Configure git identity globally for the test environment."""
    print("- Configuring git identity")
    run_cmd(["git", "config", "--global", "user.email", "matias.magni@gmail.com"], check=False)
    run_cmd(["git", "config", "--global", "user.name", "Matias J. Magni"], check=False)


def generate_rsa_key_pair(passphrase: str = "123456") -> Tuple[str, str]:
    """Generate RSA key pair using ssh-keygen (produces SSH-format public key which OPAL expects)."""
    # Always use ssh-keygen to produce SSH-format public keys that OPAL expects
    # The -m pem flag only affects private key format, public key is still in SSH format
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "opal_crypto_key"
        # Generate key pair using ssh-keygen (same as bash script)
        run_cmd([
            "ssh-keygen", "-q", "-t", "rsa", "-b", "4096", "-m", "pem",
            "-f", str(key_path), "-N", passphrase
        ])
        
        # Read public key (SSH format: ssh-rsa AAAAB3...)
        with open(f"{key_path}.pub", 'r') as f:
            public_key = f.read().strip()
        
        # Read private key and format for OPAL (replace newlines with underscores)
        with open(key_path, 'r') as f:
            private_pem = f.read()
        
        private_key_formatted = private_pem.replace('\n', '_')
        
        return public_key, private_key_formatted


def cleanup_port_7002():
    """Clean up any existing containers using port 7002."""
    print("    Cleaning up any existing containers on port 7002...")
    
    # Stop and remove opal-server-keygen if it exists
    try:
        run_cmd(["docker", "rm", "-f", "opal-server-keygen"], check=False, capture_output=False)
    except:
        pass
    
    # Find containers using port 7002
    try:
        result = run_cmd(
            ["docker", "ps", "-a", "--filter", "publish=7002", "--format", "{{.ID}}"],
            check=False
        )
        if result.stdout.strip():
            container_ids = result.stdout.strip().split('\n')
            for cid in container_ids:
                if cid.strip():
                    print(f"    Stopping existing container {cid.strip()} using port 7002...")
                    run_cmd(["docker", "stop", cid.strip()], check=False, capture_output=False)
                    run_cmd(["docker", "rm", cid.strip()], check=False, capture_output=False)
    except:
        pass
    
    # Find containers with name containing opal-server
    try:
        result = run_cmd(
            ["docker", "ps", "-a", "--filter", "name=opal-server", "--format", "{{.ID}}"],
            check=False
        )
        if result.stdout.strip():
            container_ids = result.stdout.strip().split('\n')
            for cid in container_ids:
                if cid.strip() and cid.strip() != "opal-server-keygen":
                    print(f"    Stopping container {cid.strip()}...")
                    run_cmd(["docker", "stop", cid.strip()], check=False, capture_output=False)
                    run_cmd(["docker", "rm", cid.strip()], check=False, capture_output=False)
    except:
        pass


def extract_token_from_response(response_text: str) -> Optional[str]:
    """Extract JWT token from JSON response."""
    try:
        data = json.loads(response_text)
        # Check if this is an error response
        if 'detail' in data and isinstance(data['detail'], dict) and 'error' in data['detail']:
            return None
        # Extract token from top-level or nested structure
        token = data.get('token', '')
        if not token and 'detail' in data:
            if isinstance(data['detail'], dict):
                token = data['detail'].get('token', '')
        return token if token else None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def generate_opal_keys():
    """Generate OPAL keys and tokens."""
    global OPAL_AUTH_PUBLIC_KEY, OPAL_AUTH_PRIVATE_KEY, OPAL_AUTH_PRIVATE_KEY_PASSPHRASE
    global OPAL_AUTH_MASTER_TOKEN, OPAL_CLIENT_TOKEN, OPAL_DATA_SOURCE_TOKEN
    
    print("- Generating OPAL keys")
    
    OPAL_AUTH_PRIVATE_KEY_PASSPHRASE = "123456"
    
    # Generate RSA key pair
    print("    Generating RSA key pair...")
    OPAL_AUTH_PUBLIC_KEY, OPAL_AUTH_PRIVATE_KEY = generate_rsa_key_pair(OPAL_AUTH_PRIVATE_KEY_PASSPHRASE)
    
    # Generate master token
    OPAL_AUTH_MASTER_TOKEN = os.urandom(16).hex()
    
    # Clean up any existing containers
    cleanup_port_7002()
    
    # Start temporary OPAL server for key generation
    print("    Starting OPAL server for keygen")
    # Don't use --rm so we can inspect logs if it fails
    run_cmd([
        "docker", "run", "-d",
        "--name", "opal-server-keygen",
        "-e", f"OPAL_AUTH_PUBLIC_KEY={OPAL_AUTH_PUBLIC_KEY}",
        "-e", f"OPAL_AUTH_PRIVATE_KEY={OPAL_AUTH_PRIVATE_KEY}",
        "-e", f"OPAL_AUTH_PRIVATE_KEY_PASSPHRASE={OPAL_AUTH_PRIVATE_KEY_PASSPHRASE}",
        "-e", f"OPAL_AUTH_MASTER_TOKEN={OPAL_AUTH_MASTER_TOKEN}",
        "-e", "OPAL_AUTH_JWT_AUDIENCE=https://api.opal.ac/v1/",
        "-e", "OPAL_AUTH_JWT_ISSUER=https://opal.ac/",
        "-e", "OPAL_REPO_WATCHER_ENABLED=0",
        "-p", "7002:7002",
        f"permitio/opal-server:{OPAL_IMAGE_TAG}"
    ])
    
    time.sleep(5)  # Give container more time to start
    
    # Check if container is actually running
    try:
        result = run_cmd(["docker", "ps", "--filter", "name=opal-server-keygen", "--format", "{{.Status}}"], check=False)
        if not result.stdout.strip():
            # Container might have exited, check all containers
            result = run_cmd(["docker", "ps", "-a", "--filter", "name=opal-server-keygen", "--format", "{{.Status}}"], check=False)
            if result.stdout.strip():
                print(f"    Container status: {result.stdout.strip()}")
                # Get logs to see why it exited
                result = run_cmd(["docker", "logs", "opal-server-keygen", "--tail", "30"], check=False)
                print(f"    Container logs:\n{result.stdout}")
                print("ERROR: Container exited immediately after starting")
                sys.exit(1)
    except:
        pass
    
    # Wait for OPAL server to be ready
    print("    Waiting for OPAL server to be ready...")
    if not wait_for_url("http://localhost:7002/", timeout=60):
        print("ERROR: Timeout waiting for OPAL server to start")
        # Check container status for debugging
        try:
            result = run_cmd(["docker", "ps", "-a", "--filter", "name=opal-server-keygen", "--format", "{{.Status}}"], check=False)
            print(f"Container status: {result.stdout}")
            result = run_cmd(["docker", "logs", "opal-server-keygen", "--tail", "20"], check=False)
            print(f"Container logs:\n{result.stdout}")
        except:
            pass
        sys.exit(1)
    
    # Obtain client token
    print("    Obtaining tokens")
    response = requests.post(
        'http://localhost:7002/token',
        headers={
            'Authorization': f'Bearer {OPAL_AUTH_MASTER_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={'type': 'client'},
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"ERROR: Failed to obtain OPAL_CLIENT_TOKEN (status: {response.status_code})")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    OPAL_CLIENT_TOKEN = extract_token_from_response(response.text)
    
    if not OPAL_CLIENT_TOKEN or OPAL_CLIENT_TOKEN == OPAL_AUTH_MASTER_TOKEN:
        print("ERROR: Failed to extract client token or token is same as master token")
        print(f"Response: {response.text[:200]}")
        sys.exit(1)
    
    if not OPAL_CLIENT_TOKEN.startswith("eyJ"):
        print(f"ERROR: Extracted token does not appear to be a JWT: {OPAL_CLIENT_TOKEN[:50]}...")
        sys.exit(1)
    
    print(f"    Successfully obtained client JWT token (length: {len(OPAL_CLIENT_TOKEN)})")
    
    # Obtain datasource token
    print("    Obtaining datasource token...")
    response = requests.post(
        'http://localhost:7002/token',
        headers={
            'Authorization': f'Bearer {OPAL_AUTH_MASTER_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={'type': 'datasource'},
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"ERROR: Failed to obtain OPAL_DATA_SOURCE_TOKEN (status: {response.status_code})")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    OPAL_DATA_SOURCE_TOKEN = extract_token_from_response(response.text)
    
    if not OPAL_DATA_SOURCE_TOKEN or OPAL_DATA_SOURCE_TOKEN == OPAL_AUTH_MASTER_TOKEN:
        print("ERROR: Failed to extract datasource token or token is same as master token")
        print(f"Response: {response.text[:200]}")
        sys.exit(1)
    
    if not OPAL_DATA_SOURCE_TOKEN.startswith("eyJ"):
        print(f"ERROR: Extracted datasource token does not appear to be a JWT: {OPAL_DATA_SOURCE_TOKEN[:50]}...")
        sys.exit(1)
    
    print(f"    Successfully obtained datasource JWT token (length: {len(OPAL_DATA_SOURCE_TOKEN)})")
    
    # Stop temporary server
    print("    Stopping OPAL server for keygen")
    try:
        run_cmd(["docker", "stop", "opal-server-keygen"], check=False, capture_output=False)
    except:
        pass
    try:
        run_cmd(["docker", "rm", "opal-server-keygen"], check=False, capture_output=False)
    except:
        pass
    
    time.sleep(5)
    
    # Create .env file
    print("- Create .env file")
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        env_file.unlink()
    
    # Build OPAL_DEFAULT_UPDATE_CALLBACKS JSON
    callbacks = {
        'callbacks': [[
            'http://opal_server:7002/data/callback_report',
            {
                'method': 'post',
                'process_data': False,
                'headers': {
                    'Authorization': f'Bearer {OPAL_CLIENT_TOKEN}',
                    'content-type': 'application/json'
                }
            }
        ]]
    }
    opal_default_update_callbacks = json.dumps(callbacks)
    
    # Write .env file
    with open(env_file, 'w') as f:
        f.write(f'OPAL_AUTH_PUBLIC_KEY="{OPAL_AUTH_PUBLIC_KEY}"\n')
        f.write(f'OPAL_AUTH_PRIVATE_KEY="{OPAL_AUTH_PRIVATE_KEY}"\n')
        f.write(f'OPAL_AUTH_MASTER_TOKEN="{OPAL_AUTH_MASTER_TOKEN}"\n')
        f.write(f'OPAL_CLIENT_TOKEN="{OPAL_CLIENT_TOKEN}"\n')
        f.write(f'CLIENT_TOKEN="{OPAL_CLIENT_TOKEN}"\n')
        f.write(f'OPAL_AUTH_PRIVATE_KEY_PASSPHRASE="{OPAL_AUTH_PRIVATE_KEY_PASSPHRASE}"\n')
        f.write(f'OPAL_DEFAULT_UPDATE_CALLBACKS={opal_default_update_callbacks}\n')


def prepare_policy_repo():
    """Prepare the policy repository in Gitea."""
    global OPAL_POLICY_REPO_URL, OPAL_POLICY_REPO_URL_FOR_WEBHOOK, POLICY_REPO_BRANCH
    
    print("- Preparing policy repository")
    
    # Wait for Gitea to be ready
    print("  Waiting for Gitea to be ready...")
    if not wait_for_url("http://localhost:3000", timeout=120):
        print("ERROR: Timeout waiting for Gitea to start")
        sys.exit(1)
    
    # Wait for Gitea API to be available
    print("  Waiting for Gitea to be fully initialized...")
    if not wait_for_url("http://localhost:3000/api/v1/version", timeout=120, interval=2):
        print("ERROR: Timeout waiting for Gitea to be initialized")
        sys.exit(1)
    print("  Gitea is ready!")
    
    # Create admin user
    print("  Creating initial admin user...")
    try:
        run_cmd([
            "docker", "exec", "gitea", "gitea", "admin", "user", "create",
            "--username", "gitea_admin",
            "--password", "admin123",
            "--email", "admin@gitea.local",
            "--admin",
            "--must-change-password=false"
        ], check=False, capture_output=False)
    except:
        print("  Admin user might already exist")
    
    # Prepare local repository
    print(f"  Creating temp repo for policy repository at {SCRIPT_DIR}/temp-repo...")
    temp_repo_dir = SCRIPT_DIR / "temp-repo"
    
    # Make sure we're not inside the directory we're about to delete
    current_dir = Path.cwd()
    if temp_repo_dir in current_dir.parents or temp_repo_dir == current_dir:
        os.chdir(SCRIPT_DIR)
    
    if temp_repo_dir.exists():
        print("  Removing existing temp-repo directory...")
        safe_rmtree(temp_repo_dir)
        # Give Windows time to release file handles, especially git processes
        if platform.system() == "Windows":
            time.sleep(2)  # Increased wait time for Windows
    
    # Create directory fresh
    temp_repo_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(temp_repo_dir)
    
    # Initialize git repo
    run_cmd(["git", "init"])
    run_cmd(["git", "config", "user.email", "matias.magni@gmail.com"])
    run_cmd(["git", "config", "user.name", "Matias J. Magni"])
    
    # Copy policy files
    print("  Copying policy files...")
    policy_source = SCRIPT_DIR / "opal-tests-policy-repo-main"
    if policy_source.exists():
        for item in policy_source.iterdir():
            if item.name != '.git':
                if item.is_dir():
                    shutil.copytree(item, temp_repo_dir / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, temp_repo_dir / item.name)
    
    # Create initial commit
    run_cmd(["git", "add", "."])
    run_cmd(["git", "commit", "-m", "Initial policies from opal-tests-policy-repo"])
    
    # Set up repository URLs
    OPAL_POLICY_REPO_URL = "http://gitea_admin:admin123@localhost:3000/gitea_admin/policy-repo.git"
    OPAL_POLICY_REPO_URL_FOR_WEBHOOK = "http://gitea:3000/gitea_admin/policy-repo.git"
    
    run_cmd(["git", "remote", "add", "origin", OPAL_POLICY_REPO_URL])
    
    # Check if repository exists and delete if needed
    print("  Checking if repository exists...")
    try:
        response = requests.get(
            "http://localhost:3000/api/v1/repos/gitea_admin/policy-repo",
            auth=("gitea_admin", "admin123"),
            timeout=10
        )
        if response.status_code == 200:
            print("  Repository already exists, deleting it...")
            requests.delete(
                "http://localhost:3000/api/v1/repos/gitea_admin/policy-repo",
                auth=("gitea_admin", "admin123"),
                timeout=10
            )
            time.sleep(2)
    except requests.RequestException:
        pass
    
    # Create repository via API
    print("  Creating repository via API...")
    try:
        response = requests.post(
            "http://localhost:3000/api/v1/user/repos",
            auth=("gitea_admin", "admin123"),
            headers={"Content-Type": "application/json"},
            json={"name": "policy-repo", "private": False, "auto_init": False},
            timeout=10
        )
        if response.status_code not in [201, 409]:  # 409 means already exists
            print(f"  Failed to create repository via API (status: {response.status_code})")
            print("  Trying push method...")
            run_cmd(["git", "push", "-u", "origin", "master:main"], check=False)
            run_cmd(["git", "push", "-u", "origin", "master"], check=False)
    except requests.RequestException as e:
        print(f"  Failed to create repository via API: {e}")
        print("  Trying push method...")
        run_cmd(["git", "push", "-u", "origin", "master:main"], check=False)
        run_cmd(["git", "push", "-u", "origin", "master"], check=False)
    
    # Push to repository
    print("  Pushing to repository...")
    try:
        run_cmd(["git", "push", "-u", "origin", "master:main"], check=False)
    except:
        run_cmd(["git", "push", "-u", "origin", "master"], check=False)
    
    # Create and push test branch
    POLICY_REPO_BRANCH = f"test-{random.randint(100000, 999999)}{random.randint(100000, 999999)}"
    run_cmd(["git", "checkout", "-b", POLICY_REPO_BRANCH])
    run_cmd(["git", "push", "-u", "origin", POLICY_REPO_BRANCH])
    
    # Make sure we're in script directory before cloning
    os.chdir(SCRIPT_DIR)
    
    # Clone fresh for testing
    print("  Cloning fresh repository for testing...")
    clone_dir = SCRIPT_DIR / "opal-tests-policy-repo"
    
    # Make sure we're not inside the directory we're about to delete
    current_dir = Path.cwd()
    if clone_dir in current_dir.parents or clone_dir == current_dir:
        os.chdir(SCRIPT_DIR)
    
    if clone_dir.exists():
        print("  Removing existing opal-tests-policy-repo directory...")
        safe_rmtree(clone_dir)
        # Give Windows time to release file handles, especially git processes
        if platform.system() == "Windows":
            time.sleep(2)  # Increased wait time for Windows
    
    run_cmd(["git", "clone", OPAL_POLICY_REPO_URL, str(clone_dir)])
    os.chdir(clone_dir)
    run_cmd(["git", "config", "user.email", "matias.magni@gmail.com"])
    run_cmd(["git", "config", "user.name", "Matias J. Magni"])
    run_cmd(["git", "checkout", POLICY_REPO_BRANCH])
    os.chdir(SCRIPT_DIR)
    
    # Update .env file with POLICY_REPO_BRANCH so docker-compose can use it
    print(f"  Setting POLICY_REPO_BRANCH={POLICY_REPO_BRANCH} in .env file...")
    env_file = SCRIPT_DIR / ".env"
    
    # Read existing .env file, update or add POLICY_REPO_BRANCH, then write back
    env_lines = []
    if env_file.exists():
        with open(env_file, 'r') as f:
            env_lines = f.readlines()
    
    # Remove any existing POLICY_REPO_BRANCH line
    env_lines = [line for line in env_lines if not line.startswith('POLICY_REPO_BRANCH=')]
    
    # Add the new POLICY_REPO_BRANCH
    env_lines.append(f'POLICY_REPO_BRANCH={POLICY_REPO_BRANCH}\n')
    
    # Write back to .env file
    with open(env_file, 'w') as f:
        f.writelines(env_lines)
    
    # Also set as environment variable for current process
    os.environ['POLICY_REPO_BRANCH'] = POLICY_REPO_BRANCH
    
    print(f"  ✓ POLICY_REPO_BRANCH set to {POLICY_REPO_BRANCH}")


def compose_cmd(cmd: list, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run docker compose command with the app-tests compose file."""
    compose_cmd_list = ["docker", "compose", "-f", "./docker-compose-app-tests.yml", "--env-file", ".env"] + cmd
    return run_cmd(compose_cmd_list, check=check, **kwargs)

# Verify function signature at module load
import inspect
_compose_cmd_sig = inspect.signature(compose_cmd)
if 'check' not in _compose_cmd_sig.parameters:
    print("WARNING: compose_cmd function signature mismatch! Please delete __pycache__ directories and try again.")


def strip_ansi_codes(text: str) -> str:
    """Strip ANSI escape codes from text."""
    import re
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def check_clients_logged(message: str):
    """Check if a message appears in client logs."""
    print(f"- Looking for msg '{message}' in client's logs")
    try:
        result1 = compose_cmd(["logs", "--index", "1", "opal_client", "--tail", "500"], check=False)
        result2 = compose_cmd(["logs", "--index", "2", "opal_client", "--tail", "500"], check=False)
        
        if result1.returncode != 0 or result2.returncode != 0:
            print(f"  Warning: Could not retrieve all client logs (return codes: {result1.returncode}, {result2.returncode})")
        
        # Strip ANSI codes and check both logs
        logs1_clean = strip_ansi_codes(result1.stdout) if result1.returncode == 0 else ""
        logs2_clean = strip_ansi_codes(result2.stdout) if result2.returncode == 0 else ""
        
        if message in logs1_clean or message in logs2_clean:
            print(f"  ✓ Found message in client logs")
            return
        
        # Message not found, show detailed diagnostics
        print(f"ERROR: Message '{message}' not found in client logs")
        
        # Show recent relevant logs for debugging
        print("\nRecent client-1 logs (filtered for relevant content):")
        relevant_lines1 = [line for line in logs1_clean.split('\n')[-100:] 
                          if 'PUT' in line or 'data' in line.lower() or 'policy' in line.lower() 
                          or 'error' in line.lower() or 'ERROR' in line]
        if relevant_lines1:
            for line in relevant_lines1[-30:]:  # Show last 30 relevant lines
                print(f"  {line}")
        else:
            print("  (No relevant lines found)")
            
        print("\nRecent client-2 logs (filtered for relevant content):")
        relevant_lines2 = [line for line in logs2_clean.split('\n')[-100:]
                          if 'PUT' in line or 'data' in line.lower() or 'policy' in line.lower()
                          or 'error' in line.lower() or 'ERROR' in line]
        if relevant_lines2:
            for line in relevant_lines2[-30:]:  # Show last 30 relevant lines
                print(f"  {line}")
        else:
            print("  (No relevant lines found)")
            
        sys.exit(1)
        
    except Exception as e:
        print(f"ERROR: Exception while checking client logs: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def check_no_error():
    """Check that there are no ERROR messages in client logs."""
    result = compose_cmd(["logs", "opal_client"])
    if "ERROR" in result.stdout:
        print("- Found error in logs:")
        for line in result.stdout.split('\n'):
            if 'ERROR' in line:
                print(line)
        sys.exit(1)


def test_push_policy(policy_name: str):
    """Test pushing a policy file."""
    global POLICY_REPO_BRANCH, OPAL_POLICY_REPO_URL_FOR_WEBHOOK
    print(f"- Testing pushing policy {policy_name}")
    rego_file = f"{policy_name}.rego"
    
    repo_dir = SCRIPT_DIR / "opal-tests-policy-repo"
    if not repo_dir.exists():
        print(f"ERROR: Repository directory {repo_dir} does not exist")
        sys.exit(1)
    
    os.chdir(repo_dir)
    
    run_cmd(["git", "config", "user.email", "matias.magni@gmail.com"], check=False)
    run_cmd(["git", "config", "user.name", "Matias J. Magni"], check=False)
    
    # Create the policy file
    with open(rego_file, 'w') as f:
        f.write(f"package {policy_name}\n")
    
    # Commit and push
    print(f"  Creating and committing {rego_file}...")
    run_cmd(["git", "add", rego_file])
    commit_result = run_cmd(["git", "commit", "-m", f"Add {rego_file}"], check=False)
    if commit_result.returncode != 0:
        print(f"  Warning: Git commit had issues: {commit_result.stderr}")
        # File might already be committed, check
        status_result = run_cmd(["git", "status", "--porcelain"], check=False)
        if rego_file not in status_result.stdout:
            print(f"  File appears to already be committed, continuing...")
        else:
            print(f"ERROR: Failed to commit policy file")
            sys.exit(1)
    
    print(f"  Pushing to {POLICY_REPO_BRANCH} branch...")
    push_result = run_cmd(["git", "push", "origin", POLICY_REPO_BRANCH], check=False)
    if push_result.returncode != 0:
        print(f"  Warning: Git push had issues: {push_result.stderr}")
        # Try again after a short wait
        time.sleep(2)
        push_result = run_cmd(["git", "push", "origin", POLICY_REPO_BRANCH], check=False)
        if push_result.returncode != 0:
            print(f"ERROR: Failed to push policy after retry: {push_result.stderr}")
            sys.exit(1)
    print(f"  ✓ Policy pushed successfully to repository")
    
    os.chdir(SCRIPT_DIR)
    
    # Trigger webhook with proper payload structure
    print(f"  Triggering webhook for branch {POLICY_REPO_BRANCH}...")
    try:
        # Include branch in webhook payload so server can match it
        webhook_payload = {
            "gitEvent": "git.push",
            "ref": f"refs/heads/{POLICY_REPO_BRANCH}",
            "repository": {
                "git_url": OPAL_POLICY_REPO_URL_FOR_WEBHOOK,
                "clone_url": OPAL_POLICY_REPO_URL_FOR_WEBHOOK,
                "full_name": "gitea_admin/policy-repo"
            }
        }
        
        webhook_response = requests.post(
            'http://localhost:7002/webhook',
            headers={
                'Content-Type': 'application/json',
                'x-webhook-token': 'xxxxx'
            },
            json=webhook_payload,
            timeout=10
        )
        print(f"  Webhook response: {webhook_response.status_code}")
        if webhook_response.status_code == 200:
            print(f"  Webhook accepted: {webhook_response.json()}")
        else:
            print(f"  Webhook warning: {webhook_response.text[:200]}")
    except Exception as e:
        print(f"  Warning: Webhook failed (polling will catch it): {e}")
    
    # Wait for policy to propagate - polling happens every 5 seconds
    # So we need to wait at least that long, plus some buffer
    print(f"  Waiting for policy {rego_file} to appear in logs (polling every 5s)...")
    max_retries = 30  # Increased to 30 * 3s = 90s to allow for polling cycles
    found = False
    search_msg = f"PUT /v1/policies/{rego_file} -> 200"
    
    for attempt in range(max_retries):
        time.sleep(3)
        try:
            # Check client logs - use try/except for each compose_cmd call
            result1 = None
            result2 = None
            try:
                result1 = compose_cmd(["logs", "--index", "1", "opal_client", "--tail", "200"], check=False)
            except TypeError as e:
                # Handle case where check parameter isn't accepted (shouldn't happen but just in case)
                print(f"  ERROR: compose_cmd TypeError (possible cache issue): {e}")
                print(f"  Attempting workaround...")
                # Try without check parameter as fallback
                try:
                    result1 = compose_cmd(["logs", "--index", "1", "opal_client", "--tail", "200"])
                    result1.returncode = 0  # Assume success if no exception
                except Exception as e2:
                    print(f"  Workaround also failed: {e2}")
                    result1 = subprocess.CompletedProcess([], 1, "", "")
            except Exception as e:
                print(f"  Error calling compose_cmd for client 1: {e}")
                result1 = subprocess.CompletedProcess([], 1, "", "")
            
            try:
                result2 = compose_cmd(["logs", "--index", "2", "opal_client", "--tail", "200"], check=False)
            except TypeError as e:
                print(f"  ERROR: compose_cmd TypeError (possible cache issue): {e}")
                try:
                    result2 = compose_cmd(["logs", "--index", "2", "opal_client", "--tail", "200"])
                    result2.returncode = 0
                except Exception as e2:
                    print(f"  Workaround also failed: {e2}")
                    result2 = subprocess.CompletedProcess([], 1, "", "")
            except Exception as e:
                print(f"  Error calling compose_cmd for client 2: {e}")
                result2 = subprocess.CompletedProcess([], 1, "", "")
            
            if result1 and result2 and result1.returncode == 0 and result2.returncode == 0:
                logs1_clean = strip_ansi_codes(result1.stdout)
                logs2_clean = strip_ansi_codes(result2.stdout)
                
                # Look for the policy update message
                if search_msg in logs1_clean or search_msg in logs2_clean:
                    print(f"  ✓ Policy {rego_file} found in client logs after {attempt + 1} attempts ({(attempt + 1) * 3}s)")
                    found = True
                    break
                    
        except Exception as e:
            if attempt % 5 == 0:  # Log errors every 5 attempts
                import traceback
                print(f"  Warning during log check: {type(e).__name__}: {e}")
                # Only show full traceback on first error to avoid spam
                if attempt == 0:
                    traceback.print_exc()
        
        # Check server logs periodically to see if it's processing the update
        if attempt % 5 == 0 and attempt > 0:  # Every 5 attempts (15 seconds), check server logs
            try:
                server_result = compose_cmd(["logs", "opal_server", "--tail", "100"], check=False)
                if server_result.returncode == 0:
                    server_logs = strip_ansi_codes(server_result.stdout)
                    # Check for policy-related activity
                    if rego_file in server_logs or "policy bundle" in server_logs.lower() or "webhook" in server_logs.lower():
                        print(f"  Server activity detected (attempt {attempt + 1})...")
            except:
                pass
        
        if attempt < max_retries - 1 and (attempt + 1) % 5 == 0:
            print(f"  Still waiting... ({attempt + 1}/{max_retries}, elapsed: {(attempt + 1) * 3}s)")
    
    if not found:
        print(f"ERROR: Policy {rego_file} not found in client logs after {max_retries * 3} seconds")
        print("Checking server logs for policy updates...")
        try:
            server_result = compose_cmd(["logs", "opal_server", "--tail", "200"], check=False)
            if server_result.returncode == 0:
                server_logs = strip_ansi_codes(server_result.stdout)
                print("Recent server logs (filtered for policy-related):")
                policy_lines = [line for line in server_logs.split('\n')[-100:] 
                               if 'policy' in line.lower() or rego_file in line.lower() or 'webhook' in line.lower() 
                               or 'bundle' in line.lower()]
                for line in policy_lines[:30]:  # Show first 30 matching lines
                    print(f"  {line}")
        except Exception as e:
            print(f"  Could not retrieve server logs: {e}")
        
        # Show recent client logs for debugging
        print("\nChecking recent client logs for any policy updates...")
        try:
            result1 = compose_cmd(["logs", "--index", "1", "opal_client", "--tail", "100"], check=False)
            result2 = compose_cmd(["logs", "--index", "2", "opal_client", "--tail", "100"], check=False)
            if result1.returncode == 0:
                logs1_clean = strip_ansi_codes(result1.stdout)
                print("Client-1 recent policy-related logs:")
                for line in logs1_clean.split('\n')[-50:]:
                    if 'PUT' in line or 'policy' in line.lower() or 'bundle' in line.lower():
                        print(f"  {line}")
            if result2.returncode == 0:
                logs2_clean = strip_ansi_codes(result2.stdout)
                print("Client-2 recent policy-related logs:")
                for line in logs2_clean.split('\n')[-50:]:
                    if 'PUT' in line or 'policy' in line.lower() or 'bundle' in line.lower():
                        print(f"  {line}")
        except Exception as e:
            print(f"  Could not retrieve client logs: {e}")
        
        # This will exit with error
        check_clients_logged(f"PUT /v1/policies/{rego_file} -> 200")


def test_data_publish(user: str):
    """Test publishing data for a user."""
    global OPAL_DATA_SOURCE_TOKEN
    print(f"- Testing data publish for user {user}")
    
    try:
        response = requests.post(
            'http://localhost:7002/data/config',
            headers={
                'Authorization': f'Bearer {OPAL_DATA_SOURCE_TOKEN}',
                'Content-Type': 'application/json'
            },
            json={
                "entries": [{
                    "url": "https://api.country.is/23.54.6.78",
                    "config": {},
                    "topics": ["policy_data"],
                    "dst_path": f"/users/{user}/location",
                    "save_method": "PUT"
                }]
            },
            timeout=10
        )
        print(f"  Data publish response: {response.status_code}")
        if response.status_code != 200:
            print(f"  Warning: Data publish returned status {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"  Error publishing data: {e}")
        sys.exit(1)
    
    # Wait longer for data to propagate, especially after broadcast channel restarts
    print(f"  Waiting for data update to propagate...")
    search_msg = f"PUT /v1/data/users/{user}/location -> 204"
    max_retries = 15  # 15 * 2s = 30 seconds
    found = False
    
    for attempt in range(max_retries):
        time.sleep(2)
        try:
            result1 = compose_cmd(["logs", "--index", "1", "opal_client", "--tail", "200"], check=False)
            result2 = compose_cmd(["logs", "--index", "2", "opal_client", "--tail", "200"], check=False)
            
            if result1.returncode == 0 and result2.returncode == 0:
                logs1_clean = strip_ansi_codes(result1.stdout)
                logs2_clean = strip_ansi_codes(result2.stdout)
                
                if search_msg in logs1_clean or search_msg in logs2_clean:
                    print(f"  ✓ Data update found after {attempt + 1} attempts ({(attempt + 1) * 2}s)")
                    found = True
                    break
        except Exception as e:
            if attempt % 5 == 0:
                print(f"  Warning during log check: {e}")
        
        if attempt < max_retries - 1 and (attempt + 1) % 5 == 0:
            print(f"  Still waiting for data update... ({attempt + 1}/{max_retries}, elapsed: {(attempt + 1) * 2}s)")
    
    if not found:
        print(f"ERROR: Data update not found after {max_retries * 2} seconds")
        check_clients_logged(search_msg)


def test_statistics():
    """Test statistics feature."""
    global OPAL_DATA_SOURCE_TOKEN
    print("- Testing statistics feature")
    # Make sure 2 servers & 2 clients (repeat few times cause different workers might response)
    for port in range(7002, 7004):
        for _ in range(8):
            try:
                response = requests.get(
                    f"http://localhost:{port}/stats",
                    headers={"Authorization": f"Bearer {OPAL_DATA_SOURCE_TOKEN}"},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('client_count') == 2 and data.get('server_count') == 2:
                        continue
            except:
                pass
    print("  Statistics check completed")


def clean_up(exit_code: int = 0):
    """Clean up resources."""
    # Always ensure we're in script directory before cleanup
    try:
        os.chdir(SCRIPT_DIR)
    except:
        pass  # If we can't change, continue anyway
    
    if exit_code != 0:
        print("*** Test Failed ***")
        print("")
        try:
            result = compose_cmd(["logs"])
            print(result.stdout)
        except:
            print("Could not retrieve logs")
    else:
        print("*** Test Passed ***")
        print("")
    
    try:
        compose_cmd(["down"])
    except:
        try:
            run_cmd(["docker", "compose", "-f", "./docker-compose-app-tests.yml", "down"], check=False)
        except:
            pass
    
    # Clean up directories - make sure we're not inside any of them
    cleanup_dirs = ["opal-tests-policy-repo", "temp-repo", "gitea-data", "git-repos"]
    current_dir = Path.cwd()
    
    for dir_name in cleanup_dirs:
        dir_path = SCRIPT_DIR / dir_name
        if dir_path.exists():
            # If we're inside this directory or one of its subdirectories, move out first
            if dir_path in current_dir.parents or dir_path == current_dir:
                try:
                    os.chdir(SCRIPT_DIR)
                except:
                    pass
            
            try:
                safe_rmtree(dir_path)
                if platform.system() == "Windows":
                    time.sleep(0.5)  # Give Windows time between deletions
            except Exception as e:
                # Non-fatal error during cleanup
                print(f"Warning: Could not remove {dir_name}: {e}")
    
    sys.exit(exit_code)


def main():
    """Main test function."""
    global POLICY_REPO_BRANCH
    
    # Ensure we're in the correct directory
    os.chdir(SCRIPT_DIR)
    
    # Configure git identity
    configure_git_identity()
    
    # Setup
    generate_opal_keys()
    
    try:
        # Bring up containers
        compose_cmd(["down", "--remove-orphans"])
        
        print("Starting Gitea")
        compose_cmd(["up", "-d", "gitea", "--force-recreate"])
        time.sleep(5)
        
        print("Preparing policy repository")
        prepare_policy_repo()
        
        print("Starting OPAL services")
        compose_cmd(["up", "-d", "--force-recreate"])
        time.sleep(15)
        
        # Check containers started correctly
        check_clients_logged("Connected to PubSub server")
        check_clients_logged("Got policy bundle")
        check_clients_logged("PUT /v1/data/static -> 204")
        check_no_error()
        
        # Test functionality
        test_data_publish("bob")
        test_push_policy("something")
        test_statistics()
        
        print("- Testing broadcast channel disconnection")
        compose_cmd(["restart", "broadcast_channel"])
        print("  Waiting for broadcast channel to restart and clients to reconnect...")
        time.sleep(15)  # Increased wait time for clients to reconnect after broadcast channel restart
        
        # Verify clients are still connected before continuing
        print("  Verifying clients are still connected after broadcast channel restart...")
        time.sleep(5)
        
        test_data_publish("alice")
        test_push_policy("another")
        test_data_publish("sunil")
        test_data_publish("eve")
        test_push_policy("best_one_yet")
        
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # Clear Python cache if it exists to avoid stale bytecode issues
    cache_dir = SCRIPT_DIR / "__pycache__"
    if cache_dir.exists():
        try:
            import shutil
            shutil.rmtree(cache_dir, ignore_errors=True)
        except:
            pass
    
    # Verify compose_cmd function signature is correct
    try:
        import inspect
        sig = inspect.signature(compose_cmd)
        if 'check' not in sig.parameters:
            print("ERROR: compose_cmd function signature is incorrect!")
            print("Please ensure you're running the latest version of run.py")
            sys.exit(1)
    except Exception as e:
        print(f"WARNING: Could not verify compose_cmd signature: {e}")
    
    # Retry test in case of failure to avoid flakiness
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        print(f"Running test (attempt {retry_count + 1} of {MAX_RETRIES})...")
        exit_code = main()
        if exit_code == 0:
            break
        retry_count += 1
        if retry_count < MAX_RETRIES:
            print("Test failed, retrying...")
            time.sleep(5)
    
    if retry_count >= MAX_RETRIES:
        print(f"Tests failed after {MAX_RETRIES} attempts.")
        clean_up(1)
    else:
        print("Tests passed successfully.")
        clean_up(0)
