import pytest
import os
import subprocess
import time
import requests
import docker
import shutil
from pathlib import Path


@pytest.fixture(scope="session")
def generate_opal_keys():
    """Generate OPAL keys and create an .env file."""
    print("- Generating OPAL keys")
    
    opal_private_key_passphrase = "123456"
    subprocess.run([
        "ssh-keygen", "-q", "-t", "rsa", "-b", "4096", "-m", "pem",
        "-f", "opal_crypto_key", "-N", opal_private_key_passphrase
    ], check=True)

    with open("opal_crypto_key.pub") as f:
        opal_auth_public_key = f.read().strip()
    with open("opal_crypto_key") as f:
        opal_auth_private_key = f.read().replace('\n', '_')

    os.remove("opal_crypto_key.pub")
    os.remove("opal_crypto_key")

    opal_auth_master_token = subprocess.run(
        ["openssl", "rand", "-hex", "16"], capture_output=True, text=True
    ).stdout.strip()

    env_vars = {
        "OPAL_AUTH_PRIVATE_KEY_PASSPHRASE": opal_private_key_passphrase,
        "OPAL_AUTH_MASTER_TOKEN": opal_auth_master_token,
        "OPAL_AUTH_JWT_AUDIENCE": "https://api.opal.ac/v1/",
        "OPAL_AUTH_JWT_ISSUER": "https://opal.ac/",
        "OPAL_REPO_WATCHER_ENABLED": "0",
        "OPAL_STATISTICS_ENABLED": "true"
    }

    opal_server = subprocess.Popen(["opal-server", "run"], env={**os.environ, **env_vars})
    time.sleep(2)

    opal_client_token = subprocess.run(
        ["opal-client", "obtain-token", opal_auth_master_token, "--type", "client"],
        capture_output=True, text=True
    ).stdout.strip()

    opal_data_source_token = subprocess.run(
        ["opal-client", "obtain-token", opal_auth_master_token, "--type", "datasource"],
        capture_output=True, text=True
    ).stdout.strip()

    opal_server.terminate()
    opal_server.wait()
    time.sleep(5)

    # Create .env file
    with open(".env", "w") as f:
        f.write(f"OPAL_AUTH_PUBLIC_KEY=\"{opal_auth_public_key}\"\n")
        f.write(f"OPAL_AUTH_PRIVATE_KEY=\"{opal_auth_private_key}\"\n")
        f.write(f"OPAL_AUTH_MASTER_TOKEN=\"{opal_auth_master_token}\"\n")
        f.write(f"OPAL_CLIENT_TOKEN=\"{opal_client_token}\"\n")
        f.write(f"OPAL_AUTH_PRIVATE_KEY_PASSPHRASE=\"{opal_private_key_passphrase}\"\n")
        f.write("OPAL_STATISTICS_ENABLED=true\n") 

    os.environ["OPAL_STATISTICS_ENABLED"] = "true"
    yield

    if Path(".env").exists():
        os.remove(".env")


@pytest.fixture(scope="session")
def prepare_policy_repo():
    """Clone and configure the policy repo for testing."""
    print("- Setting up policy repository")
    repo_url = os.getenv("OPAL_POLICY_REPO_URL", "git@github.com:permitio/opal-tests-policy-repo.git")
    policy_repo_branch = f"test-{os.getpid()}"

    if os.path.exists("opal-tests-policy-repo"):
        shutil.rmtree("opal-tests-policy-repo")

    result = subprocess.run(["git", "clone", repo_url, "opal-tests-policy-repo"], capture_output=True, text=True)

    if result.returncode != 0:
        print("❌ Error cloning repository:", result.stderr)
        pytest.fail("Failed to clone the policy repo")

    os.chdir("opal-tests-policy-repo")
    subprocess.run(["git", "checkout", "-b", policy_repo_branch], check=True)
    subprocess.run(["git", "push", "--set-upstream", "origin", policy_repo_branch], check=True)
    os.chdir("..")

    yield policy_repo_branch

    os.chdir("opal-tests-policy-repo")
    subprocess.run(["git", "push", "-d", "origin", policy_repo_branch], check=True)
    os.chdir("..")
    shutil.rmtree("opal-tests-policy-repo")


@pytest.fixture(scope="session")
def docker_services():
    """Start OPAL containers."""
    client = docker.from_env()
    print("- Starting Docker containers")
    client.containers.run("permitio/opal-server:latest", detach=True, ports={"7002": 7002})
    client.containers.run("permitio/opal-client:latest", detach=True, ports={"7766": 7766})
    time.sleep(10)

    yield client

    print("- Stopping Docker containers")
    for container in client.containers.list():
        container.stop()
        container.remove()