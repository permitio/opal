import pytest

import docker
from tests import utils
from tests.settings import pytest_settings, session_matrix


@pytest.fixture(scope="session")
def opal_server_image(session_matrix):
    """Builds a Docker image for the OPAL server in debug mode.

    Yields the name of the built image.

    This fixture is used to provide a working OPAL server image for the
    tests.
    """

    if pytest_settings.do_not_build_images:
        yield "permitio/opal-server:latest"
        return

    image_name = "opal_server_debug_local:latest"
    yield from utils.build_docker_image(
        "Dockerfile.server.local", image_name, session_matrix
    )


@pytest.fixture(scope="session")
def opa_image(session_matrix):
    """Builds a Docker image containing the Open Policy Agent (OPA) binary.

    Yields the name of the built image.

    This fixture is used to provide a working OPA image for the tests.
    """
    image_name = "opa"

    yield from utils.build_docker_image("Dockerfile.opa", image_name, session_matrix)


@pytest.fixture(scope="session")
def cedar_image(session_matrix):
    """Builds a Docker image containing the Cedar binary.

    Yields the name of the built image.

    This fixture is used to provide a working Cedar image for the tests.
    """
    image_name = "cedar"

    yield from utils.build_docker_image("Dockerfile.cedar", image_name, session_matrix)


@pytest.fixture(scope="session")
def opal_client_image(session_matrix):
    """Builds a Docker image containing the OPAL client binary.

    Yields the name of the built image.

    This fixture is used to provide a working OPAL client image for the
    tests.
    """
    if pytest_settings.do_not_build_images:
        yield "permitio/opal-client:latest"
        return

    image_name = "opal_client_debug_local:latest"

    yield from utils.build_docker_image(
        "Dockerfile.client.local", image_name, session_matrix
    )


@pytest.fixture(scope="session")
def opal_client_with_opa_image(session_matrix):
    """Builds a Docker image containing the OPAL client binary.

    Yields the name of the built image.

    This fixture is used to provide a working OPAL client image for the
    tests.
    """
    if pytest_settings.do_not_build_images:
        yield "permitio/opal-client:latest"
        return

    image_name = "opal_client_with_opa_debug_local:latest"

    yield from utils.build_docker_image(
        "Dockerfile.client_opa.local", image_name, session_matrix
    )
