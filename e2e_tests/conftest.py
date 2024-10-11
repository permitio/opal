import pytest
import subprocess
import time
import os

@pytest.fixture(scope="session", autouse=True)
def docker_compose_setup():
    """Spin up Docker containers for OPAL services using docker-compose."""
    compose_file = os.path.abspath("./docker-compose.yml")

    subprocess.run(["docker-compose", "-f", compose_file, "up", "-d"])
    
    # Wait for services to be up and running
    time.sleep(60)
    
    yield
    
    # Tear down the Docker services after tests
    subprocess.run(["docker-compose", "-f", compose_file, "down"])
