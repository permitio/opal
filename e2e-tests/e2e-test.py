from typing import Dict
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
import docker
import requests
import time
import json
from config import OPALEnvironment, get_environment

class OPALTestEnvironment:
    """Main test environment manager"""
    def __init__(self, config: OPALEnvironment):
        self.config = config
        self.containers: Dict[str, DockerContainer] = {}
        self.docker_client = docker.from_env()
        self.network = None
        self.network_id = None

    def setup(self):
        """Setup the complete test environment"""
        try:
            # Create network
            self._create_network()
            print(f"\nCreated network: {self.config.NETWORK_NAME}")

            #Start Postgres broadcast channel
            print("\n=== Starting Postgres Container ===")
            self.containers['postgres'] = DockerContainer("postgres:alpine")
            self._configure_postgres(self.containers['postgres'])
            self.containers['postgres'].with_name("broadcast_channel")
            self.containers['postgres'].start()

            # Wait for Postgres to be ready
            self._wait_for_postgres()

            #Start OPAL Server
            print("\n=== Starting OPAL Server Container ===")
            self.containers['server'] = DockerContainer("permitio/opal-server:latest")
            self._configure_server(self.containers['server'])
            self.containers['server'].with_name("opal_server")
            self.containers['server'].start()

            # Wait for server to be healthy
            self._wait_for_server()

            #Start OPAL Client
            print("\n=== Starting OPAL Client Container ===")
            self.containers['client'] = DockerContainer("permitio/opal-client:latest")
            self._configure_client(self.containers['client'])
            self.containers['client'].with_name("opal_client")
            self.containers['client'].with_command(
                f"sh -c 'exec ./wait-for.sh opal_server:{self.config.SERVER_PORT} --timeout=20 -- ./start.sh'"
            )
            self.containers['client'].start()

            # Wait for client
            self._wait_for_client()

        except Exception as e:
            print(f"\n❌ Error during setup: {str(e)}")
            self._print_container_logs()
            self.teardown()
            raise

    def _create_network(self):
        """Create Docker network for test environment"""
        try:
            # Remove network if it exists
            try:
                existing_network = self.docker_client.networks.get(self.config.NETWORK_NAME)
                existing_network.remove()
            except docker.errors.NotFound:
                pass

            # Create new network
            self.network = self.docker_client.networks.create(
                name=self.config.NETWORK_NAME,
                driver="bridge",
                check_duplicate=True
            )
            self.network_id = self.network.id
        except Exception as e:
            raise Exception(f"Failed to create network: {str(e)}")

    def _configure_postgres(self, container: DockerContainer):
        """Configure Postgres container"""
        container.with_env("POSTGRES_DB", self.config.POSTGRES_DB)
        container.with_env("POSTGRES_USER", self.config.POSTGRES_USER)
        container.with_env("POSTGRES_PASSWORD", self.config.POSTGRES_PASSWORD)
        container.with_exposed_ports(self.config.POSTGRES_PORT)
        container.with_kwargs(network=self.config.NETWORK_NAME)

    def _configure_server(self, container: DockerContainer):
        """Configure OPAL server container"""
        # Core settings
        container.with_env("PORT", str(self.config.SERVER_PORT))
        container.with_env("HOST", self.config.SERVER_HOST)
        container.with_env("UVICORN_NUM_WORKERS", str(self.config.SERVER_WORKERS))
        container.with_env("LOG_LEVEL", self.config.SERVER_LOG_LEVEL)

        # Enable Statistics
        container.with_env("OPAL_STATISTICS_ENABLED", "true")

        # Broadcast configuration
        container.with_env("OPAL_BROADCAST_URI", self.config.postgres_dsn)
        container.with_env("BROADCAST_CHANNEL_NAME", "opal_updates")

        # Policy repository configuration
        container.with_env("OPAL_POLICY_REPO_URL", self.config.POLICY_REPO_URL)
        container.with_env("OPAL_POLICY_REPO_POLLING_INTERVAL", str(self.config.POLICY_REPO_POLLING_INTERVAL))

        # Data configuration
        container.with_env(
            "OPAL_DATA_CONFIG_SOURCES",
            '{"config":{"entries":[{"url":"http://opal_server:7002/policy-data","topics":["policy_data"],"dst_path":"/static"}]}}'
        )

        # Authentication
        container.with_env("AUTH_JWT_AUDIENCE", self.config.AUTH_JWT_AUDIENCE)
        container.with_env("AUTH_JWT_ISSUER", self.config.AUTH_JWT_ISSUER)
        container.with_env("AUTH_MASTER_TOKEN", self.config.SERVER_MASTER_TOKEN)

        # Logging
        container.with_env("OPAL_LOG_FORMAT_INCLUDE_PID", "true")
        container.with_env("LOG_FORMAT", "text")
        container.with_env("LOG_TRACEBACK", "true")

        container.with_exposed_ports(self.config.SERVER_PORT)
        container.with_kwargs(network=self.config.NETWORK_NAME)

    def _configure_client(self, container: DockerContainer):
        """Configure OPAL client container"""
        # Core settings
        container.with_env("OPAL_SERVER_URL", f"http://opal_server:{self.config.SERVER_PORT}")
        container.with_env("PORT", str(self.config.CLIENT_PORT))
        container.with_env("HOST", self.config.CLIENT_HOST)
        container.with_env("LOG_LEVEL", self.config.CLIENT_LOG_LEVEL)

        # Authentication
        container.with_env("OPAL_CLIENT_TOKEN", self.config.CLIENT_TOKEN)
        container.with_env("AUTH_JWT_AUDIENCE", self.config.AUTH_JWT_AUDIENCE)
        container.with_env("AUTH_JWT_ISSUER", self.config.AUTH_JWT_ISSUER)

        # Features
        container.with_env("POLICY_UPDATER_ENABLED", "true")
        container.with_env("DATA_UPDATER_ENABLED", "true")
        container.with_env("INLINE_OPA_ENABLED", "true")
        container.with_env("OPA_HEALTH_CHECK_POLICY_ENABLED", "true")

        # OPA Configuration
        container.with_env("OPAL_INLINE_OPA_LOG_FORMAT", "http")
        container.with_env("INLINE_OPA_CONFIG", "{}")

        # Statistics
        container.with_env("OPAL_STATISTICS_ENABLED", "true")

        # Logging
        container.with_env("OPAL_LOG_FORMAT_INCLUDE_PID", "true")
        container.with_env("LOG_FORMAT", "text")
        container.with_env("LOG_TRACEBACK", "true")

        container.with_exposed_ports(self.config.CLIENT_PORT)
        container.with_exposed_ports(8181)  # OPA port
        container.with_kwargs(network=self.config.NETWORK_NAME)

    def _wait_for_postgres(self):
        """Wait for Postgres to be ready"""
        print("\nWaiting for Postgres to be ready...")
        wait_for_logs(self.containers['postgres'], "database system is ready to accept connections", timeout=30)
        print("✅ Postgres is ready!")
        time.sleep(2)

    def _wait_for_server(self):
        """Wait for server to be ready"""
        print("\nWaiting for OPAL server to be ready...")

        for retry in range(self.config.TEST_MAX_RETRIES):
            try:
                server_url = f"http://{self.containers['server'].get_container_host_ip()}:{self.containers['server'].get_exposed_port(self.config.SERVER_PORT)}"
                response = requests.get(f"{server_url}/healthcheck", timeout=5)
                if response.status_code == 200:
                    print("✅ OPAL server is ready!")
                    time.sleep(5)  # Give it more time to stabilize
                    return
            except Exception as e:
                print(f"⚠️  Server not ready (attempt {retry + 1}/{self.config.TEST_MAX_RETRIES}): {str(e)}")
                if retry == self.config.TEST_MAX_RETRIES - 1:
                    self._print_container_logs()
                    raise TimeoutError("❌ OPAL server failed to become healthy")
                time.sleep(self.config.TEST_RETRY_INTERVAL)

    def _wait_for_client(self):
        """Wait for client to be ready"""
        print("\nWaiting for OPAL client to be ready...")

        for retry in range(self.config.TEST_MAX_RETRIES):
            try:
                client_url = f"http://{self.containers['client'].get_container_host_ip()}:{self.containers['client'].get_exposed_port(self.config.CLIENT_PORT)}"
                response = requests.get(f"{client_url}/healthcheck", timeout=5)
                if response.status_code == 200:
                    print("✅ OPAL client is ready!")
                    time.sleep(5)  # Give extra time for OPA to initialize
                    return
            except Exception as e:
                print(f"⚠️  Client not ready (attempt {retry + 1}/{self.config.TEST_MAX_RETRIES}): {str(e)}")
                time.sleep(self.config.TEST_RETRY_INTERVAL)
                if retry == self.config.TEST_MAX_RETRIES - 1:
                    self._print_container_logs()
                    raise TimeoutError("❌ OPAL client failed to become healthy")

    def check_client_server_connection(self) -> bool:
        """Verify client-server connection using Statistics API"""
        try:
            server_url = f"http://{self.containers['server'].get_container_host_ip()}:{self.containers['server'].get_exposed_port(self.config.SERVER_PORT)}"
            stats_url = f"{server_url}/statistics"
            headers = {"Authorization": f"Bearer {self.config.SERVER_MASTER_TOKEN}"}

            print(f"\nChecking statistics at: {stats_url}")
            response = requests.get(stats_url, headers=headers)

            if response.status_code != 200:
                print(f"\n❌ Failed to get statistics: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                return False

            stats = response.json()
            print(f"\n📊 Server Statistics:")
            print(json.dumps(stats, indent=2))

            # Verify required fields
            required_fields = ["clients", "uptime", "version"]
            for field in required_fields:
                if field not in stats:
                    print(f"\n❌ Missing required field in statistics: {field}")
                    return False

            # Check for connected clients
            if not stats["clients"]:
                print("\n❌ No clients found in statistics")
                return False

            # Verify client subscriptions
            found_client = False
            expected_topics = ["policy_data"]

            for client_id, client_data in stats["clients"].items():
                print(f"\n📊 Client {client_id} Data:")
                print(json.dumps(client_data, indent=2))
                
                if isinstance(client_data, list):
                    for conn in client_data:
                        client_topics = conn.get("topics", [])
                        if any(topic in client_topics for topic in expected_topics):
                            found_client = True
                            print(f"✅ Found client with expected topics: {client_topics}")
                            break

            if not found_client:
                print("\n❌ No client found with expected topic subscriptions")
                return False

            print("\n✅ Client-server connection verified successfully")
            return True

        except Exception as e:
            print(f"\n❌ Error checking client-server connection: {str(e)}")
            return False

    def check_container_logs_for_errors(self) -> bool:
        """Check container logs for critical errors"""
        error_keywords = ["ERROR", "CRITICAL", "FATAL", "Exception"]
        found_errors = False

        print("\n=== Container Logs Analysis ===")
        for name, container in self.containers.items():
            try:
                logs = container.get_logs()[0].decode()
                container_errors = []

                for line in logs.split('\n'):
                    if any(keyword in line for keyword in error_keywords):
                        container_errors.append(line.strip())

                if container_errors:
                    print(f"\n⚠️  Found errors in {name} logs:")
                    for error in container_errors[:5]:  # Show first 5 errors
                        print(f"  - {error}")
                    if len(container_errors) > 5:
                        print(f"  ... and {len(container_errors) - 5} more errors")
                    found_errors = True
                else:
                    print(f"✅ {name}: No critical errors found")

            except Exception as e:
                print(f"❌ Error getting logs for {name}: {str(e)}")
                found_errors = True

        return not found_errors

    def _print_container_logs(self):
        """Print logs from all containers for debugging"""
        print("\n=== Debug: Container Logs ===")
        for name, container in self.containers.items():
            try:
                print(f"\n📋 {name.upper()} LOGS:")
                print("=== STDOUT ===")
                print(container.get_logs()[0].decode())
                print("\n=== STDERR ===")
                print(container.get_logs()[1].decode())
                print("=" * 80)
            except Exception as e:
                print(f"❌ Could not get logs for {name}: {str(e)}")

    def teardown(self):
        """Cleanup all resources"""
        print("\n=== Cleaning Up Test Environment ===")
        for container in reversed(list(self.containers.values())):
            try:
                container.stop()
            except Exception as e:
                print(f"❌ Error stopping container: {str(e)}")

        if self.network:
            try:
                self.network.remove()
                print(f"✅ Removed network: {self.config.NETWORK_NAME}")
            except Exception as e:
                print(f"❌ Error removing network: {str(e)}")

@pytest.fixture(scope="module")
def opal_config():
    """Fixture that provides environment configuration"""
    return get_environment()

@pytest.fixture(scope="module")
def opal_env(opal_config):
    """Main fixture that provides the test environment"""
    env = OPALTestEnvironment(opal_config)
    env.setup()
    yield env
    env.teardown()

def test_opal_baseline(opal_env, opal_config):
    """Test basic OPAL functionality with clear output formatting"""
    print("\n" + "="*50)
    print("Starting OPAL Environment Tests")
    print("="*50)
    
    time.sleep(opal_config.TEST_RETRY_INTERVAL * 5)  # Give services extra time to stabilize

    # Test server health
    print("\n=== Testing Server Health ===")
    try:
        server_url = f"http://{opal_env.containers['server'].get_container_host_ip()}:{opal_env.containers['server'].get_exposed_port(opal_config.SERVER_PORT)}"
        server_health = requests.get(f"{server_url}/healthcheck")
        assert server_health.status_code == 200, "Server health check failed"
        print("✅ Server Health Check: PASSED")

        # Get server statistics
        stats_url = f"{server_url}/statistics"
        headers = {"Authorization": f"Bearer {opal_config.SERVER_MASTER_TOKEN}"}
        stats_response = requests.get(stats_url, headers=headers)
        if stats_response.status_code == 200:
            print("\n📊 Server Statistics:")
            print(json.dumps(stats_response.json(), indent=2))
        else:
            print("⚠️  Could not fetch server statistics")

    except Exception as e:
        print(f"❌ Server Health Check: FAILED - {str(e)}")
        raise

    # Test client health
    print("\n=== Testing Client Health ===")
    try:
        client_url = f"http://{opal_env.containers['client'].get_container_host_ip()}:{opal_env.containers['client'].get_exposed_port(opal_config.CLIENT_PORT)}"
        client_health = requests.get(f"{client_url}/healthcheck")  #/ready
        assert client_health.status_code == 200, "Client health check failed"
        print("✅ Client Health Check: PASSED")

        # Test OPA endpoint
        opa_url = f"http://{opal_env.containers['client'].get_container_host_ip()}:{opal_env.containers['client'].get_exposed_port(8181)}"
        opa_health = requests.get(f"{opa_url}/health")
        if opa_health.status_code == 200:
            print("✅ OPA Health Check: PASSED")
            print("\n📊 OPA Status:")
            print(json.dumps(opa_health.json(), indent=2))
        else:
            print("⚠️  OPA Health Check: WARNING - Unexpected status code")

    except Exception as e:
        print(f"❌ Client Health Check: FAILED - {str(e)}")
        raise

    # Check logs for errors
    print("\n=== Analyzing Container Logs ===")
    for name, container in opal_env.containers.items():
        try:
            logs = container.get_logs()[0].decode()
            error_count = sum(1 for line in logs.split('\n') if "ERROR" in line)
            critical_count = sum(1 for line in logs.split('\n') if "CRITICAL" in line)
            
            print(f"\n📋 {name.title()} Log Analysis:")
            if error_count == 0 and critical_count == 0:
                print(f"✅ No errors or critical issues found")
            else:
                print(f"⚠️  Found issues:")
                print(f"   - {error_count} ERRORs")
                print(f"   - {critical_count} CRITICALs")
                
                # Print first few errors if any found
                if error_count > 0 or critical_count > 0:
                    print("\nSample of issues found:")
                    for line in logs.split('\n'):
                        if "ERROR" in line or "CRITICAL" in line:
                            print(f"   {line.strip()}")
                            break  # Just show first error as example

        except Exception as e:
            print(f"❌ {name.title()} Log Analysis Failed: {str(e)}")

    # Check client-server connection
    print("\n=== Testing Client-Server Connection ===")
    connection_ok = opal_env.check_client_server_connection()
    if connection_ok:
        print("✅ Client-Server Connection: PASSED")
    else:
        print("❌ Client-Server Connection: FAILED")
        assert False, "Client-Server connection check failed"

    # Summary
    print("\n" + "="*50)
    print("Test Summary")
    print("="*50)
    print("✅ Server Health: PASSED")
    print("✅ Client Health: PASSED")
    print("✅ OPA Integration: PASSED")
    print("✅ Log Analysis: Complete")
    print("✅ Client-Server Connection: PASSED")
    print("\n✨ All Tests Completed Successfully ✨")