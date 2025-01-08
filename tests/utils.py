import asyncio
import json
import os
import platform
import re
import subprocess
import sys
import time

import aiohttp
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from git import Repo
from testcontainers.core.utils import setup_logger

import docker
from tests.containers.opal_server_container import OpalServerContainer
from tests.settings import pytest_settings

logger = setup_logger(__name__)


def compose(filename="docker-compose-app-tests.yml", *args):
    """Helper function to run docker compose commands with the given arguments.

    Assumes `docker-compose-app-tests.yml` is the compose file and `.env` is the environment file.
    """
    command = [
        "docker",
        "compose",
        "-f",
        filename,
        "--env-file",
        ".env",
    ] + list(args)
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Compose command failed: {result.stderr.strip()}")
    return result.stdout


def build_docker_image(docker_file: str, image_name: str, session_matrix: dict):
    """Build the Docker image from the Dockerfile.server.local file in the
    tests/docker directory."""

    docker_client = docker.from_env()

    print(f"Building Docker image '{image_name}'...")

    image = None
    if (not session_matrix["is_first"]) or (pytest_settings.skip_rebuild_images):
        exists = any(image_name in image.tags for image in docker_client.images.list())
        if exists:
            image = docker_client.images.get(image_name)

    if not image:
        if "tests" in os.path.abspath(__file__):
            logger.info(f"Right now the file is {os.path.abspath(__file__)}")
            context_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "opal")
            )
        else:
            context_path = ".."
        dockerfile_path = os.path.join(os.path.dirname(__file__), "docker", docker_file)
        logger.info(f"Context path: {context_path}, Dockerfile path: {dockerfile_path}")

        # Ensure the Dockerfile exists
        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")

        logger.debug(f"Building Docker image from {dockerfile_path}...")

        try:
            # Build the Docker image
            image, logs = docker_client.images.build(
                path=context_path,
                dockerfile=dockerfile_path,
                tag=image_name,
                rm=True,
            )
            # Print build logs
            for log in logs:
                logger.debug(log.get("stream", "").strip())
        except Exception as e:
            raise RuntimeError(f"Failed to build Docker image: {e}")

        logger.debug(f"Docker image '{image_name}' built successfully.")

    yield image_name

    if session_matrix["is_final"]:
        # Optionally, clean up the image after the test session
        try:
            if pytest_settings.keep_images:
                return

            image.remove(force=True)
            print(f"Docker image '{image.id}' removed.")
        except Exception as cleanup_error:
            print(
                f"Failed to remove Docker image '{image_name}'{image.id}: {cleanup_error}"
            )


def remove_pytest_opal_networks():
    """Remove all Docker networks with names starting with 'pytest_opal_'."""
    try:
        client = docker.from_env()
        networks = client.networks.list()

        for network in networks:
            if network.name.startswith("pytest_opal_"):
                try:
                    logger.debug(f"Removing network: {network.name}")
                    network.remove()
                except Exception as e:
                    logger.debug(f"Failed to remove network {network.name}: {e}")
        logger.debug("Cleanup complete!")
    except Exception as e:
        logger.debug(f"Error while accessing Docker: {e}")


def generate_ssh_key_pair():
    # Generate a private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,  # Standard public exponent
        key_size=2048,  # Key size in bits
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
    return private_key_pem.decode("utf-8"), public_key_openssh.decode("utf-8")


async def opal_authorize(user: str, policy_url: str):
    """Test if the user is authorized based on the current policy."""

    # HTTP headers and request payload
    headers = {"Content-Type": "application/json"}
    data = {
        "input": {"user": user, "action": "read", "object": "id123", "type": "finance"}
    }

    # Send POST request to OPA
    response = requests.post(policy_url, headers=headers, json=data)

    allowed = False
    # Parse the JSON response
    response_json = response.json()
    assert "result" in response_json, response_json
    allowed = response.json()["result"]
    logger.debug(
        f"Authorization test result: {user} is {'ALLOWED' if allowed else 'NOT ALLOWED'}."
    )

    return allowed


def wait_policy_repo_polling_interval(opal_server_container: OpalServerContainer):
    # Allow time for the update to propagate
    propagation_time = 5  # seconds
    for i in range(
        int(opal_server_container.settings.polling_interval) + propagation_time, 0, -1
    ):
        logger.debug(
            f"waiting for OPAL server to pull the new policy {i} secondes left",
            end="\r",
        )
        time.sleep(1)


def is_port_available(port):
    # Determine the platform (Linux or macOS)
    system_platform = platform.system().lower()

    # Run the appropriate netstat command based on the platform
    if system_platform == "darwin":  # macOS
        result = subprocess.run(
            ["netstat", "-an"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # macOS 'netstat' shows *.<port> format for listening ports
        if f".{port} " in result.stdout:
            return False  # Port is in use
    else:  # Linux
        result = subprocess.run(
            ["netstat", "-an"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Linux 'netstat' shows 0.0.0.0:<port> or :::<port> format for listening ports
        if f":{port} " in result.stdout or f"::{port} " in result.stdout:
            return False  # Port is in use

    return True  # Port is available


def find_available_port(starting_port=5001):
    port = starting_port
    while True:
        if is_port_available(port):
            return port
        port += 1


def publish_data_update(
    server_url: str,
    server_route: str,
    token: str,
    src_url: str = None,
    reason: str = "",
    topics: list[str] = ["policy_data"],
    data: str = None,
    src_config: dict[str, any] = None,
    dst_path: str = "",
    save_method: str = "PUT",
):
    """Publish a DataUpdate through an OPAL-server.

    Args:
        server_url (str): URL of the OPAL-server.
        server_route (str): Route in the server for updates.
        token (str): JWT token for authentication.
        src_url (Optional[str]): URL of the data source.
        reason (str): Reason for the update.
        topics (Optional[List[str]]): Topics for the update.
        data (Optional[str]): Data to include in the update.
        src_config (Optional[Dict[str, Any]]): Fetching config as JSON.
        dst_path (str): Destination path in the client data store.
        save_method (str): Method to save data (e.g., "PUT").
    """
    entries = []
    if src_url:
        entries.append(
            {
                "url": src_url,
                "data": json.loads(data) if data else None,
                "topics": topics or ["policy_data"],  # Ensure topics is not None
                "dst_path": dst_path,
                "save_method": save_method,
                "config": src_config,
            }
        )

    update_payload = {"entries": entries, "reason": reason}

    async def send_update():
        headers = {"content-type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                f"{server_url}{server_route}", json=update_payload
            ) as response:
                if response.status == 200:
                    return "Event Published Successfully"
                else:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Failed with status {response.status}: {error_text}"
                    )

    return asyncio.run(send_update())


def publish_data_update_with_curl(
    server_url: str,
    server_route: str,
    token: str,
    src_url: str = None,
    reason: str = "",
    topics: list[str] = ["policy_data"],
    data: str = None,
    src_config: dict[str, any] = None,
    dst_path: str = "",
    save_method: str = "PUT",
):
    """Publish a DataUpdate through an OPAL-server using curl.
    # Example usage
    # publish_data_update_with_curl("http://example.com", "/update", "your-token", src_url="http://data-source")

    Args:
        server_url (str): URL of the OPAL-server.
        server_route (str): Route in the server for updates.
        token (str): JWT token for authentication.
        src_url (Optional[str]): URL of the data source.
        reason (str): Reason for the update.
        topics (Optional[List[str]]): Topics for the update.
        data (Optional[str]): Data to include in the update.
        src_config (Optional[Dict[str, Any]]): Fetching config as JSON.
        dst_path (str): Destination path in the client data store.
        save_method (str): Method to save data (e.g., "PUT").
    """
    entries = []
    if src_url:
        entries.append(
            {
                "url": src_url,
                "data": json.loads(data) if data else None,
                "topics": topics or ["policy_data"],  # Ensure topics is not None
                "dst_path": dst_path,
                "save_method": save_method,
                "config": src_config,
            }
        )

    update_payload = {"entries": entries, "reason": reason}

    # Prepare headers for the curl command
    headers = [
        "Content-Type: application/json",
    ]
    if token:
        headers.append(f"Authorization: Bearer {token}")

    # Build the curl command
    curl_command = [
        "curl",
        "-X",
        "POST",
        f"{server_url}{server_route}",
        "-H",
        " -H ".join([f'"{header}"' for header in headers]),
        "-d",
        json.dumps(update_payload),
    ]

    # Execute the curl command
    try:
        result = subprocess.run(
            curl_command, capture_output=True, text=True, check=True
        )
        if result.returncode == 0:
            return "Event Published Successfully"
        else:
            raise RuntimeError(
                f"Failed with status {result.returncode}: {result.stderr}"
            )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error executing curl: {e.stderr}")


def get_client_and_server_count(json_data):
    """Extracts the client_count and server_count from a given JSON string.

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


def install_opal_server_and_client():
    logger.debug("- Installing opal-server and opal-client from pip...")

    try:
        # Install opal-server and opal-client
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "opal-server", "opal-client"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        # Verify installation
        opal_server_installed = (
            subprocess.run(
                ["opal-server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            ).returncode
            == 0
        )

        opal_client_installed = (
            subprocess.run(
                ["opal-client"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            ).returncode
            == 0
        )

        if not opal_server_installed or not opal_client_installed:
            logger.debug(
                "Installation failed: opal-server or opal-client is not available."
            )
            sys.exit(1)

        logger.debug("- opal-server and opal-client successfully installed.")

    except subprocess.CalledProcessError:
        logger.debug("Installation failed: pip command encountered an error.")
        sys.exit(1)


def export_env(varname, value):
    """Exports an environment variable with a given value and updates the
    current environment.

    Args:
        varname (str): The name of the environment variable to set.
        value (str): The value to assign to the environment variable.

    Returns:
        str: The value assigned to the environment variable.

    Side Effects:
        Prints the export statement to the console and sets the environment variable.
    """

    logger.debug(f"export {varname}={value}")
    os.environ[varname] = value

    return value


def remove_env(varname):
    """Removes an environment variable from the current environment.

    Args:
        varname (str): The name of the environment variable to remove.

    Returns:
        None

    Side Effects:
        Prints the unset statement to the console and removes the environment variable.
    """
    logger.debug(f"unset {varname}")
    del os.environ[varname]

    return


def create_localtunnel(port=8000):
    try:
        # Run the LocalTunnel command
        process = subprocess.Popen(
            ["lt", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Read output line by line
        for line in iter(process.stdout.readline, ""):
            # Match the public URL from LocalTunnel output
            match = re.search(r"https://[a-z0-9\-]+\.loca\.lt", line)
            if match:
                public_url = match.group(0)
                logger.debug(f"Public URL: {public_url}")
                return public_url

    except Exception as e:
        logger.debug(f"Error starting LocalTunnel: {e}")

    return None


import sys


def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to exit the program without a traceback
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log or print the exception details
    logger.debug(f"Uncaught exception: {exc_type.__name__}: {exc_value}")


# Set the global exception handler
sys.excepthook = global_exception_handler
