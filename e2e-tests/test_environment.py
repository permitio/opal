"""Test environment management"""
import logging
import time
from typing import Dict
import json
import docker
import requests
from testcontainers.core.container import DockerContainer 
from testcontainers.core.waiting_utils import wait_for_logs
from config import OPALEnvironment
from container_config import (
    configure_postgres,
    configure_server,
    configure_client
)

# Configure logging
logger = logging.getLogger(__name__)

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
            self._create_network()
            logger.info(f"Created network: {self.config.NETWORK_NAME}")

            # Start Postgres broadcast channel
            logger.info("Starting Postgres Container") 
            self.containers['postgres'] = DockerContainer("postgres:alpine")
            configure_postgres(self.containers['postgres'], self.config)
            self.containers['postgres'].with_name("broadcast_channel")
            self.containers['postgres'].start()

            # Wait for Postgres
            self._wait_for_postgres()

            # Start OPAL Server
            logger.info("Starting OPAL Server Container")
            self.containers['server'] = DockerContainer("permitio/opal-server:latest")
            configure_server(self.containers['server'], self.config)
            self.containers['server'].with_name("opal_server")
            self.containers['server'].start()

            # Wait for server
            self._wait_for_server()

            # Start OPAL Client  
            logger.info("Starting OPAL Client Container")
            self.containers['client'] = DockerContainer("permitio/opal-client:latest")
            configure_client(self.containers['client'], self.config)
            self.containers['client'].with_name("opal_client")
            self.containers['client'].with_command(
                f"sh -c 'exec ./wait-for.sh opal_server:{self.config.SERVER_PORT} --timeout=20 -- ./start.sh'"
            )
            self.containers['client'].start()

            # Wait for client
            self._wait_for_client()

        except Exception as e:
            logger.error(f"Error during setup: {str(e)}")
            self._log_container_status()
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

    def _wait_for_postgres(self):
        """Wait for Postgres to be ready"""
        logger.info("Waiting for Postgres to be ready...")
        wait_for_logs(self.containers['postgres'], "database system is ready to accept connections", timeout=30)
        logger.info("Postgres is ready")
        time.sleep(2)

    def _wait_for_server(self):
        """Wait for server to be ready with retries"""
        logger.info("Waiting for OPAL server to be ready...")

        for retry in range(self.config.TEST_MAX_RETRIES):
            try:
                server_url = f"http://{self.containers['server'].get_container_host_ip()}:{self.containers['server'].get_exposed_port(self.config.SERVER_PORT)}"
                response = requests.get(f"{server_url}/healthcheck", timeout=5)
                if response.status_code == 200:
                    logger.info("OPAL server is ready")
                    time.sleep(5)  # Allow stabilization
                    return
            except Exception as e:
                logger.warning(f"Server not ready (attempt {retry + 1}/{self.config.TEST_MAX_RETRIES}): {str(e)}")
                if retry == self.config.TEST_MAX_RETRIES - 1:
                    self._log_container_status()
                    raise TimeoutError("OPAL server failed to become healthy")
                time.sleep(self.config.TEST_RETRY_INTERVAL)

    def _wait_for_client(self):
        """Wait for client to be ready with retries"""
        logger.info("Waiting for OPAL client to be ready...")
        
        for retry in range(self.config.TEST_MAX_RETRIES):
            try:
                client_url = f"http://{self.containers['client'].get_container_host_ip()}:{self.containers['client'].get_exposed_port(self.config.CLIENT_PORT)}"
                response = requests.get(f"{client_url}/healthcheck", timeout=5)
                if response.status_code == 200:
                    logger.info("OPAL client is ready")
                    time.sleep(5)  # Allow OPA initialization
                    return
            except Exception as e:
                logger.warning(f"Client not ready (attempt {retry + 1}/{self.config.TEST_MAX_RETRIES}): {str(e)}")
                if retry == self.config.TEST_MAX_RETRIES - 1:
                    self._log_container_status()
                    raise TimeoutError("OPAL client failed to become healthy")
                time.sleep(self.config.TEST_RETRY_INTERVAL)
                
    def _log_container_status(self):
        """Log container statuses and logs for debugging"""
        logger.debug("=== Container Status ===")
        for name, container in self.containers.items():
            try:
                logger.debug(f"=== {name.upper()} LOGS ===")
                logger.debug("STDOUT:")
                logger.debug(container.get_logs()[0].decode())
                logger.debug("STDERR:") 
                logger.debug(container.get_logs()[1].decode())
            except Exception as e:
                logger.error(f"Could not get logs for {name}: {str(e)}")

    def teardown(self):
        """Cleanup all resources"""
        logger.info("Cleaning up test environment")
        for name, container in reversed(list(self.containers.items())):
            try:
                container.stop()
                logger.info(f"Stopped container: {name}")
            except Exception as e:
                logger.error(f"Error stopping container {name}: {str(e)}")

        if self.network:
            try:
                self.network.remove()
                logger.info(f"Removed network: {self.config.NETWORK_NAME}")
            except Exception as e:
                logger.error(f"Error removing network: {str(e)}")