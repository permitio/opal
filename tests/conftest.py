import threading
import time
import debugpy
import docker
import pytest
from testcontainers.core.waiting_utils import wait_for_logs
from tests import utils
from tests.broadcast_container import BroadcastContainer
from tests.opal_client_container import OpalClientContainer
from tests.opal_server_container import OpalServerContainer

from . import settings as s

# wait up to 30 seconds for the debugger to attach
def cancel_wait_for_client_after_timeout():
    time.sleep(30)
    debugpy.wait_for_client.cancel()

t = threading.Thread(target=cancel_wait_for_client_after_timeout)
t.start()
debugpy.wait_for_client()

@pytest.fixture(scope="session")
def opal_network():
    
    print("Removing all networks with names starting with 'pytest_opal_'")
    utils.remove_pytest_opal_networks()

    client = docker.from_env()
    network = client.networks.create(s.OPAL_TESTS_NETWORK_NAME, driver="bridge")
    yield network.name
    print("Removing network")
    network.remove()
    print("Network removed")    


@pytest.fixture(scope="session")
def broadcast_channel(opal_network: str):
    with BroadcastContainer(network=opal_network).with_network_aliases("broadcast_channel") as container:
        yield container


@pytest.fixture(scope="session")
def opal_server(opal_network: str, broadcast_channel: BroadcastContainer):
    
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

    opal_broadcast_uri = f"http://{ip_address}:{exposed_port}"

    with OpalServerContainer(network=opal_network, opal_broadcast_uri=opal_broadcast_uri).with_network_aliases("opal_server") as container:

        container.get_wrapped_container().reload()
        print(container.get_wrapped_container().id) 
        wait_for_logs(container, "Clone succeeded")
        yield container


@pytest.fixture(scope="session")
def opal_client(opal_network: str, opal_server: OpalServerContainer):
   
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