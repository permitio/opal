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
    yield utils.build_docker_image("Dockerfile.server.local", image_name)



@pytest.fixture(scope="session")
def opa_image():
    """Builds a Docker image containing the Open Policy Agent (OPA) binary.

    Yields the name of the built image.

    This fixture is used to provide a working OPA image for the tests.
    """
    image_name = "opa"

    yield utils.build_docker_image("Dockerfile.opa", image_name)


@pytest.fixture(scope="session")
def cedar_image():
    """Builds a Docker image containing the Cedar binary.

    Yields the name of the built image.

    This fixture is used to provide a working Cedar image for the tests.
    """
    image_name = "cedar"

    yield utils.build_docker_image("Dockerfile.cedar", image_name)

@pytest.fixture(scope="session")
def opal_client_image():
    """Builds a Docker image containing the OPAL client binary.

    Yields the name of the built image.

    This fixture is used to provide a working OPAL client image for the
    tests.
    """
    image_name = "opal_client_debug_local"

    yield utils.build_docker_image("Dockerfile.client.local", image_name)
