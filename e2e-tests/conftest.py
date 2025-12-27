import pytest
import requests
import time
from pathlib import Path

# Define the path to the docker-compose.yml file
@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return Path(__file__).parent / "docker-compose.yml"

# Define a project name for docker-compose to isolate test runs
@pytest.fixture(scope="session")
def docker_compose_project_name():
    return "opal_e2e_tests"

@pytest.fixture(scope="session")
def opal_server_url(docker_ip, docker_services):
    """Ensures OPAL server is running and returns its URL."""
    # `port_for` takes a container port and returns the corresponding host port
    port = docker_services.port_for("opal_server", 7002)
    url = f"http://{docker_ip}:{port}"
    # Wait until the server is responsive
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: requests.get(f"{url}/health").status_code == 200
    )
    return url

@pytest.fixture(scope="session")
def opal_client_url(docker_ip, docker_services):
    """Ensures OPAL client is running and returns its URL."""
    port = docker_services.port_for("opal_client", 7000)
    url = f"http://{docker_ip}:{port}"
    # Wait until the client is responsive
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: requests.get(f"{url}/health").status_code == 200
    )
    return url

@pytest.fixture(scope="session")
def opa_url(docker_ip, docker_services):
    """Ensures OPA is running (via OPAL client) and returns its URL."""
    port = docker_services.port_for("opal_client", 8181)
    url = f"http://{docker_ip}:{port}"
    # Wait until OPA is responsive
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: requests.get(f"{url}/health").status_code == 200
    )
    return url
