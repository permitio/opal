import os
import time
import subprocess
import requests
import pytest
from typing import Generator


# Configuration constants
DOCKER_COMPOSE_FILE = "docker/docker-compose-with-statistics.yml"
SERVER_URL = "http://localhost:7002"
CLIENT_URL = "http://localhost:7766"
HEALTH_CHECK_TIMEOUT = 60
HEALTH_CHECK_INTERVAL = 2


@pytest.fixture(scope="session")
def docker_services() -> Generator[None, None, None]:
    """Use existing Docker Compose services and ensure they're healthy."""
    # Check if services are already running
    _wait_for_service_health()
    
    # Don't start or stop services - use existing ones
    yield


def _wait_for_service_health():
    """Wait for OPAL server to respond to health checks."""
    start_time = time.time()
    
    while time.time() - start_time < HEALTH_CHECK_TIMEOUT:
        try:
            response = requests.get(f"{SERVER_URL}/healthcheck", timeout=5)
            if response.status_code == 200:
                # Give services a bit more time to fully initialize
                time.sleep(5)
                return
        except requests.exceptions.RequestException:
            pass
        
        time.sleep(HEALTH_CHECK_INTERVAL)
    
    pytest.fail(f"OPAL server failed to become healthy within {HEALTH_CHECK_TIMEOUT} seconds")


@pytest.fixture
def server_url(docker_services) -> str:
    """Provide the OPAL server base URL."""
    return SERVER_URL


@pytest.fixture
def client_url(docker_services) -> str:
    """Provide the OPAL client base URL."""
    return CLIENT_URL


@pytest.fixture
def get_container_logs():
    """Helper function to retrieve Docker container logs."""
    def _get_logs(service_name: str) -> str:
        try:
            result = subprocess.run([
                "docker-compose", "-f", DOCKER_COMPOSE_FILE, "logs", service_name
            ], capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"Error getting logs for {service_name}: {e}"
    
    return _get_logs


@pytest.fixture
def api_client():
    """Helper for making API requests with proper error handling."""
    def _make_request(url: str, method: str = "GET", **kwargs):
        try:
            response = requests.request(method, url, timeout=10, **kwargs)
            return response
        except requests.exceptions.RequestException as e:
            pytest.fail(f"API request failed: {e}")
    
    return _make_request