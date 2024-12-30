import os
import shutil
import tempfile
import threading
import time
import debugpy
import docker
import json
import pytest
from typing import List
from testcontainers.core.waiting_utils import wait_for_logs
from tests import utils
from tests.containers.broadcast_container import BroadcastContainer
from tests.containers.gitea_container import GiteaContainer
from tests.containers.opal_client_container import OpalClientContainer
from tests.containers.opal_server_container import OpalServerContainer

from tests.containers.settings.gitea_settings import GiteaSettings
from tests.containers.settings.opal_server_settings import OpalServerSettings
from tests.containers.settings.opal_client_settings import OpalClientSettings

from testcontainers.core.utils import setup_logger

from testcontainers.core.network import Network

from . import settings as s

logger = setup_logger(__name__)
s.dump_settings()

# wait up to 30 seconds for the debugger to attach
def cancel_wait_for_client_after_timeout():
    time.sleep(5)
    debugpy.wait_for_client.cancel()

t = threading.Thread(target=cancel_wait_for_client_after_timeout)
t.start()
print("Waiting for debugger to attach... 30 seconds timeout")
debugpy.wait_for_client()

@pytest.fixture(scope="session")
def temp_dir():
    # Setup: Create a temporary directory
    dir_path = tempfile.mkdtemp()
    print(f"Temporary directory created: {dir_path}")
    yield dir_path

    # Teardown: Clean up the temporary directory
    shutil.rmtree(dir_path)
    print(f"Temporary directory removed: {dir_path}")

repo_name = "opal-example-policy-repo"

@pytest.fixture(scope="session")
def opal_network():
    
    print("Removing all networks with names starting with 'pytest_opal_'")
    utils.remove_pytest_opal_networks()

    client = docker.from_env()
    network = client.networks.create(s.OPAL_TESTS_NETWORK_NAME, driver="bridge")
    yield network
    print("Removing network")
    network.remove()
    print("Network removed")    

@pytest.fixture(scope="session")
def gitea_server(opal_network: Network):
    
    with GiteaContainer(
        GiteaSettings(
            container_name="gitea_server",
            repo_name="test_repo",
            temp_dir=os.path.join(os.path.dirname(__file__), "temp"),
            network=opal_network,
            data_dir=os.path.join(os.path.dirname(__file__), "policies"),
            gitea_base_url="http://localhost:3000"
        ),
        network=opal_network
        ) as gitea_container: 
        
        gitea_container.deploy_gitea()
        gitea_container.init_repo()
        yield gitea_container

@pytest.fixture(scope="session")
def broadcast_channel(opal_network: Network):
    with BroadcastContainer(opal_network) as container:
        yield container


@pytest.fixture(scope="session")
def number_of_opal_servers():
    return 2

@pytest.fixture(scope="session")
def opal_server(opal_network: Network, broadcast_channel: BroadcastContainer, gitea_server: GiteaContainer, request, number_of_opal_servers: int):
    # Get the number of containers from the request parameter
    #num_containers = getattr(request, "number_of_opal_servers", 1)  # Default to 1 if not provided

    print(f"number of opal servers: {number_of_opal_servers}")

    if not broadcast_channel:
        raise ValueError("Missing 'broadcast_channel' container.")
    
    ip_address = broadcast_channel.get_container_host_ip()
    exposed_port = broadcast_channel.get_exposed_port(5432)

    opal_broadcast_uri = f"postgres://test:test@broadcast_channel:5432"

    containers = []  # List to store container instances

    for i in range(number_of_opal_servers):
        container_name = f"opal_server_{i+1}"

        container = OpalServerContainer(
            OpalServerSettings(
                opal_broadcast_uri=opal_broadcast_uri,
                container_name=container_name,
                container_index=i+1,
                statistics_enabled="false",
                policy_repo_url=f"http://{gitea_server.settings.container_name}:{gitea_server.settings.port_http}/{gitea_server.settings.username}/{gitea_server.settings.repo_name}",
                image="permitio/opal-server:latest"
            ),
            network=opal_network
        )

        container.start()
        container.get_wrapped_container().reload()
        print(f"Started container: {container_name}, ID: {container.get_wrapped_container().id}")
        wait_for_logs(container, "Clone succeeded")
        containers.append(container)

    yield containers

    # Cleanup: Stop and remove all containers
    for container in containers:
        container.stop()

@pytest.fixture(scope="session")
def number_of_opal_clients():
    return 2

@pytest.fixture(scope="session")
def opal_client(opal_network: Network, opal_server: List[OpalServerContainer], request, number_of_opal_clients: int):
    # Get the number of clients from the request parameter
    #num_clients = getattr(request, "number_of_opal_clients", 1)  # Default to 1 if not provided

    print(f"number of opal clients: {number_of_opal_clients}")

    if not opal_server or len(opal_server) == 0:
        raise ValueError("Missing 'opal_server' container.")
    
    opal_server_url = f"http://{opal_server[0].settings.container_name}:7002"#{opal_server[0].settings.port}"
    client_token = opal_server[0].obtain_OPAL_tokens()["client"]
    callbacks = json.dumps(
        {
            "callbacks": [
                [
                    f"{opal_server_url}/data/callback_report",
                    {
                        "method": "post",
                        "process_data": False,
                        "headers": {
                            "Authorization": f"Bearer {client_token}",
                            "content-type": "application/json",
                        },
                    },
                ]
            ]
        }
    )


    containers = []  # List to store OpalClientContainer instances

    for i in range(number_of_opal_clients):
        container_name = f"opal_client_{i+1}"  # Unique name for each client

        container = OpalClientContainer(
            OpalClientSettings(
                image="permitio/opal-client:latest",
                container_name=container_name,
                container_index=i+1,
                opal_server_url=opal_server_url,
                client_token=client_token,
                default_update_callbacks=callbacks
            ),
            network=opal_network
        )

        container.start()
        print(f"Started OpalClientContainer: {container_name}, ID: {container.get_wrapped_container().id}")
        containers.append(container)

    yield containers

    # Cleanup: Stop and remove all client containers
    for container in containers:
        container.stop()

@pytest.fixture(scope="session", autouse=True)
def setup(opal_server, opal_client):
    yield
    if s.OPAL_TESTS_DEBUG:
        debugpy.breakpoint()
        s.dump_settings()
        input("Press enter to shutdown...")
        #time.sleep(3600)  # Giving us some time to inspect the containers