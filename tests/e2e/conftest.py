import pytest
from pathlib import Path
from .utils.docker_manager import DockerManager
from .utils.http_client import OpalHttpClient
from .utils.log_parser import LogParser
from .utils.wait_utils import wait_for


@pytest.fixture(scope="session")
def docker_manager():
    """
    Manages Docker Compose lifecycle for entire test session.

    Yields:
        DockerManager instance
    """
    compose_file = Path(__file__).parent / "docker_compose.yml"
    manager = DockerManager(
        compose_file=compose_file,
        project_name="opal-e2e-tests"
    )

    manager.down(remove_volumes=True)

    yield manager

    manager.down(remove_volumes=True)


@pytest.fixture(scope="session")
def docker_services(docker_manager):
    """
    Brings up Docker services and waits for them to be healthy.

    Args:
        docker_manager: DockerManager fixture

    Yields:
        DockerManager instance with running services
    """
    docker_manager.up(detach=True)

    print("\nWaiting for services to become healthy...")

    docker_manager.wait_for_healthy("broadcast_channel", timeout=60)
    print("  ✓ broadcast_channel is healthy")

    docker_manager.wait_for_healthy("opal_server", timeout=60)
    print("  ✓ opal_server is healthy")

    docker_manager.wait_for_healthy("opal_client", timeout=60)
    print("  ✓ opal_client is healthy")

    print("All services are healthy and ready for testing\n")

    yield docker_manager


@pytest.fixture
def server_client(docker_services):
    """
    HTTP client for OPAL Server.

    Args:
        docker_services: Docker services fixture

    Yields:
        OpalHttpClient configured for server
    """
    with OpalHttpClient(base_url="http://localhost:17002") as client:
        yield client


@pytest.fixture
def client_client(docker_services):
    """
    HTTP client for OPAL Client.

    Args:
        docker_services: Docker services fixture

    Yields:
        OpalHttpClient configured for client
    """
    with OpalHttpClient(base_url="http://localhost:17000") as client:
        yield client


@pytest.fixture
def opa_client(docker_services):
    """
    HTTP client for OPA.

    Args:
        docker_services: Docker services fixture

    Yields:
        OpalHttpClient configured for OPA
    """
    with OpalHttpClient(base_url="http://localhost:18181") as client:
        yield client


@pytest.fixture
def server_logs(docker_services):
    """
    Access to OPAL Server logs.

    Args:
        docker_services: Docker services fixture

    Returns:
        LogParser for server logs
    """
    return LogParser(docker_services, "opal_server")


@pytest.fixture
def client_logs(docker_services):
    """
    Access to OPAL Client logs.

    Args:
        docker_services: Docker services fixture

    Returns:
        LogParser for client logs
    """
    return LogParser(docker_services, "opal_client")


@pytest.fixture
def wait_for_condition():
    """
    Generic wait utility with timeout and retry.

    Returns:
        wait_for function
    """
    return wait_for
