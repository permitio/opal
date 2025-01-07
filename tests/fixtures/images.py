import pytest
from settings import pytest_settings

import docker
from tests import utils


@pytest.fixture(scope="session")
def opal_server_image(session_matrix):
    """Builds a Docker image for the OPAL server in debug mode.

    Yields the name of the built image.

    This fixture is used to provide a working OPAL server image for the
    tests.
    """
    image_name = "opal_server_debug_local:latest"
    image_name = f"permitio/opal-server"
    yield from utils.build_docker_image("Dockerfile.client.local", image_name, session_matrix)
    return
    yield from utils.build_docker_image("Dockerfile.server.local", image_name, session_matrix)



@pytest.fixture(scope="session")
def opa_image(session_matrix):
    """Builds a Docker image containing the Open Policy Agent (OPA) binary.

    Yields the name of the built image.

    This fixture is used to provide a working OPA image for the tests.
    """
    image_name = "opa"
    image_name = f"openpolicyagent/opa"
    yield from utils.build_docker_image("Dockerfile.client.local", image_name, session_matrix)
    return
    yield from utils.build_docker_image("Dockerfile.opa", image_name, session_matrix)


@pytest.fixture(scope="session")
def cedar_image(session_matrix):
    """Builds a Docker image containing the Cedar binary.

    Yields the name of the built image.

    This fixture is used to provide a working Cedar image for the tests.
    """
    image_name = "cedar"
    image_name = f"heroku/cedar:14"
    yield from utils.build_docker_image("Dockerfile.client.local", image_name, session_matrix)
    return
    yield from utils.build_docker_image("Dockerfile.cedar", image_name, session_matrix)

@pytest.fixture(scope="session")
def opal_client_image(session_matrix):
    """Builds a Docker image containing the OPAL client binary.

    Yields the name of the built image.

    This fixture is used to provide a working OPAL client image for the
    tests.
    """
    image_name = "opal_client_debug_local"
    image_name = f"permitio/opal-client"
    yield from utils.build_docker_image("Dockerfile.client.local", image_name, session_matrix)
    return

    yield from utils.build_docker_image("Dockerfile.client.local", image_name, session_matrix)
