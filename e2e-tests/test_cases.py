"""Test cases for OPAL integration tests"""
import logging
import json
import time
import pytest
import requests
from config import OPALEnvironment, get_environment
from test_environment import OPALTestEnvironment

logger = logging.getLogger(__name__)

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
    """Test basic OPAL functionality"""
    logger.info("Starting OPAL Environment Tests")
    
    time.sleep(opal_config.TEST_RETRY_INTERVAL * 5)  # Allow services to stabilize

    # Test server health
    logger.info("Testing Server Health")
    server_url = f"http://{opal_env.containers['server'].get_container_host_ip()}:{opal_env.containers['server'].get_exposed_port(opal_config.SERVER_PORT)}"
    server_health = requests.get(f"{server_url}/healthcheck")
    assert server_health.status_code == 200, "Server health check failed"
    logger.info("Server health check passed")

    # Test client health 
    logger.info("Testing Client Health")
    client_url = f"http://{opal_env.containers['client'].get_container_host_ip()}:{opal_env.containers['client'].get_exposed_port(opal_config.CLIENT_PORT)}"
    client_health = requests.get(f"{client_url}/healthcheck")
    assert client_health.status_code == 200, "Client health check failed"
    logger.info("Client health check passed")

    # Test OPA endpoint
    logger.info("Testing OPA Health")
    opa_url = f"http://{opal_env.containers['client'].get_container_host_ip()}:{opal_env.containers['client'].get_exposed_port(8181)}"
    opa_health = requests.get(f"{opa_url}/health")
    assert opa_health.status_code == 200, "OPA health check failed"
    logger.info("OPA health check passed")

    # Check server statistics
    logger.info("Checking Server Statistics")
    stats_url = f"{server_url}/statistics"
    headers = {"Authorization": f"Bearer {opal_config.SERVER_MASTER_TOKEN}"}
    stats_response = requests.get(stats_url, headers=headers)
    assert stats_response.status_code == 200, f"Failed to get statistics: HTTP {stats_response.status_code}"
    stats_data = stats_response.json()
    logger.info("Server Statistics: %s", json.dumps(stats_data, indent=2))

    # Check for errors in logs
    logger.info("Checking Container Logs")
    for name, container in opal_env.containers.items():
        logs = container.get_logs()[0].decode()
        error_count = sum(1 for line in logs.split('\n') if "ERROR" in line)
        critical_count = sum(1 for line in logs.split('\n') if "CRITICAL" in line)
        
        if error_count > 0 or critical_count > 0:
            logger.error(f"Found errors in {name} logs:")
            logger.error(f"- {error_count} ERRORs")
            logger.error(f"- {critical_count} CRITICALs")
            assert False, f"Found {error_count + critical_count} errors in {name} logs"
        else:
            logger.info(f"{name}: No errors found in logs")

    logger.info("All basic health checks completed successfully")