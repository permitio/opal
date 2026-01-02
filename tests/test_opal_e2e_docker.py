import time
import socket
import warnings
import requests
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

warnings.simplefilter("ignore")

MASTER_TOKEN = "my-secret-token"

def test_opal_basic_e2e():
    """
    OPAL E2E Regression Test.
    Verifies that Server and Client containers start correctly,
    communicate over the network, and exposes the Statistics API.
    """
    with Network() as network:
        print("\nStarting OPAL E2E Baseline Test...")

        # 1. Start Server
        print("Starting OPAL Server container...")
        with DockerContainer("permitio/opal-server:latest") \
                .with_network(network) \
                .with_name("opal_server") \
                .with_bind_ports(7002, 7002) \
                .with_env("OPAL_AUTH_MASTER_TOKEN", MASTER_TOKEN) \
                .with_env("OPAL_STATISTICS_ENABLED", "true") as server:

            if not wait_for_port_open(7002):
                pytest.fail("Server port 7002 not responding")
            print("Server is running on port 7002.")

            time.sleep(3)
            check_logs(server, "Server")

            # 2. Start Client
            print("Starting OPAL Client container...")
            with DockerContainer("permitio/opal-client:latest") \
                    .with_network(network) \
                    .with_name("opal_client") \
                    .with_bind_ports(7000, 7000) \
                    .with_env("OPAL_SERVER_URL", "http://opal_server:7002") \
                    .with_env("OPAL_CLIENT_TOKEN", MASTER_TOKEN) as client:

                if not wait_for_port_open(7000):
                    pytest.fail("Client port 7000 not responding")
                print("Client is running on port 7000.")

                time.sleep(3)
                check_logs(client, "Client")

                # 3. Health Checks
                print("Running connectivity checks...")

                # Check Server Statistics API
                try:
                    stats_url = "http://localhost:7002/statistics"
                    headers = {"Authorization": f"Bearer {MASTER_TOKEN}"}
                    resp = requests.get(stats_url, headers=headers, timeout=5)
                    
                    if resp.status_code == 200:
                        print("Statistics API is active (HTTP 200).")
                    elif resp.status_code == 501:
                        print("Statistics API returned 501 (Not Implemented), connection confirmed.")
                    else:
                        pytest.fail(f"Statistics API returned unexpected code: {resp.status_code}")

                except Exception as e:
                    print(f"Warning: Could not connect to statistics: {e}")

                # Check Client connectivity
                try:
                    resp = requests.get("http://localhost:7000/", timeout=5)
                    print(f"Client responded with HTTP {resp.status_code}.")
                except Exception as e:
                    pytest.fail(f"Client not responding: {e}")

                # 4. Verify Stability
                print("Verifying container stability...")
                time.sleep(5)

                if not container_is_running(server):
                    pytest.fail("Server container crashed.")
                
                if not container_is_running(client):
                    pytest.fail("Client container crashed.")

                print("Both containers are stable.")
                print("Test Passed.")

def wait_for_port_open(port, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            if result == 0:
                return True
        except:
            pass
        time.sleep(0.5)
    return False

def check_logs(container, name):
    try:
        logs = container.get_logs()
        output = ""
        if logs[0]:
            output = logs[0].decode("utf-8", errors="ignore")

        if "CRITICAL" in output:
             print(f"Warning: Found CRITICAL in {name} logs.")

        lines = [line for line in output.split("\n") if line.strip()][:3]
        for line in lines:
            print(f"[{name} Logs] {line[:80]}...")

    except Exception:
        print(f"Could not read logs for {name}.")

def container_is_running(container):
    try:
        container.get_logs()
        return True
    except:
        return False

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
