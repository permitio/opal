"""Validation utilities"""
import logging
import json
import requests
from config import OPALEnvironment
from test_environment import OPALTestEnvironment

logger = logging.getLogger(__name__)

def validate_statistics(stats: dict) -> bool:
    """Validate statistics data structure and content"""
    required_fields = ["clients", "uptime", "version"]
    for field in required_fields:
        if field not in stats:
            logger.error(f"Missing required field in statistics: {field}")
            return False

    if not stats["clients"]:
        logger.error("No clients found in statistics")
        return False

    # Verify client subscriptions
    found_client = False
    expected_topics = ["policy_data"]

    for client_id, client_data in stats["clients"].items():
        logger.info(f"Client {client_id} Data: {json.dumps(client_data, indent=2)}")
        
        if isinstance(client_data, list):
            for conn in client_data:
                client_topics = conn.get("topics", [])
                if any(topic in client_topics for topic in expected_topics):
                    found_client = True
                    logger.info(f"Found client with expected topics: {client_topics}")
                    break

    if not found_client:
        logger.error("No client found with expected topic subscriptions")
        return False

    return True

def check_client_server_connection(env: OPALTestEnvironment) -> bool:
    """Verify client-server connection using Statistics API"""
    try:
        server_url = f"http://{env.containers['server'].get_container_host_ip()}:{env.containers['server'].get_exposed_port(env.config.SERVER_PORT)}"
        stats_url = f"{server_url}/statistics"
        headers = {"Authorization": f"Bearer {env.config.SERVER_MASTER_TOKEN}"}

        logger.info(f"Checking statistics at: {stats_url}")
        response = requests.get(stats_url, headers=headers)

        if response.status_code != 200:
            logger.error(f"Failed to get statistics: HTTP {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False

        stats = response.json()
        logger.info("Server Statistics: %s", json.dumps(stats, indent=2))

        if not validate_statistics(stats):
            return False

        logger.info("Client-server connection verified successfully")
        return True

    except Exception as e:
        logger.error(f"Error checking client-server connection: {str(e)}")
        return False

def check_container_logs_for_errors(env: OPALTestEnvironment) -> bool:
    """Analyze container logs for critical errors"""
    error_keywords = ["ERROR", "CRITICAL", "FATAL", "Exception"]
    found_errors = False

    logger.info("Analyzing container logs")
    for name, container in env.containers.items():
        try:
            logs = container.get_logs()[0].decode()
            container_errors = [
                line.strip() for line in logs.split('\n')
                if any(keyword in line for keyword in error_keywords)
            ]

            if container_errors:
                logger.warning(f"Found errors in {name} logs:")
                for error in container_errors[:5]:  # Show first 5 errors
                    logger.warning(f"{name}: {error}")
                if len(container_errors) > 5:
                    logger.warning(f"... and {len(container_errors) - 5} more errors")
                found_errors = True
            else:
                logger.info(f"{name}: No critical errors found")

        except Exception as e:
            logger.error(f"Error getting logs for {name}: {str(e)}")
            found_errors = True

    return not found_errors