import os
import shutil
import tempfile
import threading
import time
import debugpy
import docker
import pytest
from testcontainers.core.waiting_utils import wait_for_logs
from tests import utils
from tests.containers.broadcast_container import BroadcastContainer
from tests.containers.gitea_container import GiteaContainer
from tests.containers.opal_client_container import OpalClientContainer
from tests.containers.opal_server_container import OpalServerContainer

from tests.containers.settings.gitea_settings import GiteaSettings
from tests.containers.settings.opal_server_settings import OpalServerSettings

from testcontainers.core.network import Network

from . import settings as s

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

            GITEA_CONTAINER_NAME="test_container",
            repo_name="test_repo",
            temp_dir=os.path.join(os.path.dirname(__file__), "temp"),
            network=opal_network,
            data_dir=os.path.dirname(__file__),
            gitea_base_url="http://localhost:3000"
        )
        ) as gitea_container: 
        
        gitea_container.deploy_gitea()
        gitea_container.init_repo()
        yield gitea_container

@pytest.fixture(scope="session")
def broadcast_channel(opal_network: Network):
    with BroadcastContainer(opal_network) as container:
        yield container


@pytest.fixture(scope="session")
def opal_server(opal_network: Network, broadcast_channel: BroadcastContainer):
    
#    debugpy.breakpoint()
    if not broadcast_channel:
        raise ValueError("Missing 'broadcast_channel' container.")
       
    # Get container IP and exposed port
    #network_settings = broadcast_channel.attrs['NetworkSettings'] 
    #ip_address = network_settings['Networks'][list(network_settings['Networks'].keys())[0]]['IPAddress']
    #ports = network_settings['Ports']
    #exposed_port = ports['5432/tcp'][0]['HostPort'] if ports and '5432/tcp' in ports else 5432  # Default to 5432

    ip_address = broadcast_channel.get_container_host_ip()
    exposed_port = broadcast_channel.get_exposed_port(5432)

    #opal_broadcast_uri = f"http://{ip_address}:{exposed_port}"
    opal_broadcast_uri = f"postgres://test:test@broadcast_channel:5432"
    
    with OpalServerContainer(
        OpalServerSettings(
        network=opal_network, opal_broadcast_uri=opal_broadcast_uri)
        ).with_network_aliases("opal_server") as container:

        container.get_wrapped_container().reload()
        print(container.get_wrapped_container().id) 
        wait_for_logs(container, "Clone succeeded")
        yield container


@pytest.fixture(scope="session")
def opal_client(opal_network: Network, opal_server: OpalServerContainer):
   
    with OpalClientContainer(network=opal_network).with_network_aliases("opal_client") as container:
        wait_for_logs(container, "")
        yield container


@pytest.fixture(scope="session", autouse=True)
def setup(opal_server, opal_client):
    yield
    if s.OPAL_TESTS_DEBUG:
        debugpy.breakpoint()
        s.dump_settings()
        input("Press enter to shutdown...")
        #time.sleep(3600)  # Giving us some time to inspect the containers