import pytest

import docker
from tests import utils


@pytest.fixture(scope="session")
def opal_server_image():
    docker_client = docker.from_env()
    image_name = "opal_server_debug_local"

    yield utils.build_docker_image("Dockerfile.server.local", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")


@pytest.fixture(scope="session")
def opa_image():
    docker_client = docker.from_env()
    image_name = "opa"

    yield utils.build_docker_image("Dockerfile.opa", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")


@pytest.fixture(scope="session")
def cedar_image():
    docker_client = docker.from_env()
    image_name = "cedar"

    yield utils.build_docker_image("Dockerfile.cedar", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")


@pytest.fixture(scope="session")
def opal_client_image():
    docker_client = docker.from_env()
    image_name = "opal_client_debug_local"

    yield utils.build_docker_image("Dockerfile.client.local", image_name)

    # Optionally, clean up the image after the test session
    try:
        docker_client.images.remove(image=image_name, force=True)
        print(f"Docker image '{image_name}' removed.")
    except Exception as cleanup_error:
        print(f"Failed to remove Docker image '{image_name}': {cleanup_error}")
