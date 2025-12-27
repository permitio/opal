"""
PyTest Configuration and Fixtures for OPAL E2E Tests

This module provides shared fixtures and utilities for the E2E test suite.
Includes Docker orchestration, service URL configuration, and helper functions.
"""

import pytest
import requests
import time
import logging
from pathlib import Path
from typing import Dict, Callable

# Configure logging for better test debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Docker Compose Configuration
# ============================================================================

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    """
    Provides the path to the docker-compose.yml file.
    
    Returns:
        Path: Path object pointing to docker-compose.yml
    """
    compose_file = Path(__file__).parent / "docker-compose.yml"
    assert compose_file.exists(), f"docker-compose.yml not found at {compose_file}"
    return compose_file


@pytest.fixture(scope="session")
def docker_compose_project_name():
    """
    Provides a unique project name for docker-compose to isolate test runs.
    
    Returns:
        str: Project name for docker-compose
    """
    return "opal_e2e_tests"


# ============================================================================
# Service URL Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def opal_server_url(docker_ip, docker_services):
    """
    Ensures OPAL server is running and returns its URL.
    
    Waits up to 90 seconds for the server to become responsive.
    
    Args:
        docker_ip: IP address to access Docker services
        docker_services: pytest-docker services manager
        
    Returns:
        str: Base URL for OPAL server (e.g., "http://localhost:7002")
    """
    port = docker_services.port_for("opal_server", 7002)
    url = f"http://{docker_ip}:{port}"
    
    logger.info(f"Waiting for OPAL Server at {url}")
    
    docker_services.wait_until_responsive(
        timeout=90.0,
        pause=0.1,
        check=lambda: is_service_healthy(f"{url}/health", "OPAL Server")
    )
    
    logger.info(f"OPAL Server is ready at {url}")
    return url


@pytest.fixture(scope="session")
def opal_client_url(docker_ip, docker_services):
    """
    Ensures OPAL client is running and returns its URL.
    
    Waits up to 90 seconds for the client to become responsive.
    
    Args:
        docker_ip: IP address to access Docker services
        docker_services: pytest-docker services manager
        
    Returns:
        str: Base URL for OPAL client (e.g., "http://localhost:7766")
    """
    port = docker_services.port_for("opal_client", 7000)
    url = f"http://{docker_ip}:{port}"
    
    logger.info(f"Waiting for OPAL Client at {url}")
    
    docker_services.wait_until_responsive(
        timeout=90.0,
        pause=0.1,
        check=lambda: is_service_healthy(f"{url}/health", "OPAL Client")
    )
    
    logger.info(f"OPAL Client is ready at {url}")
    return url


@pytest.fixture(scope="session")
def opa_url(docker_ip, docker_services):
    """
    Ensures OPA is running (via OPAL client) and returns its URL.
    
    Waits up to 90 seconds for OPA to become responsive.
    
    Args:
        docker_ip: IP address to access Docker services
        docker_services: pytest-docker services manager
        
    Returns:
        str: Base URL for OPA (e.g., "http://localhost:8181")
    """
    port = docker_services.port_for("opal_client", 8181)
    url = f"http://{docker_ip}:{port}"
    
    logger.info(f"Waiting for OPA at {url}")
    
    docker_services.wait_until_responsive(
        timeout=90.0,
        pause=0.1,
        check=lambda: is_service_healthy(f"{url}/health", "OPA")
    )
    
    logger.info(f"OPA is ready at {url}")
    return url


# ============================================================================
# Service State Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def docker_compose_logs(docker_services):
    """
    Captures logs from all services after tests have run.
    
    Useful for debugging test failures and validating log output.
    
    Args:
        docker_services: pytest-docker services manager
        
    Returns:
        Dict[str, str]: Dictionary mapping service names to their log output
    """
    logs = {}
    services = ["broadcast_channel", "opal_server", "opal_client"]
    
    for service in services:
        try:
            container = docker_services.get_service(service).get_container()
            log_output = container.logs().decode('utf-8', errors='replace')
            logs[service] = log_output
            logger.info(f"Captured {len(log_output)} bytes of logs from {service}")
        except Exception as e:
            error_msg = f"Could not retrieve logs for {service}: {str(e)}"
            logs[service] = error_msg
            logger.warning(error_msg)
    
    return logs


@pytest.fixture(scope="session")
def service_stats(opal_client_url, opal_server_url):
    """
    Provides a function to fetch current service statistics.
    
    Returns:
        Callable: Function that returns current statistics from OPAL services
    """
    def get_stats():
        stats = {}
        
        try:
            response = requests.get(f"{opal_client_url}/statistics", timeout=5)
            if response.status_code == 200:
                stats["client"] = response.json()
        except Exception as e:
            stats["client"] = {"error": str(e)}
        
        try:
            response = requests.get(f"{opal_server_url}/statistics", timeout=5)
            if response.status_code == 200:
                stats["server"] = response.json()
        except Exception as e:
            stats["server"] = {"error": str(e)}
        
        return stats
    
    return get_stats


# ============================================================================
# Helper Functions
# ============================================================================

def is_service_healthy(url: str, service_name: str = "Service", timeout: int = 5) -> bool:
    """
    Check if a service is healthy by querying its health endpoint.
    
    Args:
        url: Full URL to the health endpoint
        service_name: Name of the service (for logging)
        timeout: Request timeout in seconds
        
    Returns:
        bool: True if service is healthy, False otherwise
    """
    try:
        response = requests.get(url, timeout=timeout)
        
        if response.status_code == 200:
            logger.debug(f"{service_name} health check passed")
            return True
        else:
            logger.debug(
                f"{service_name} health check failed: "
                f"status={response.status_code}, body={response.text[:100]}"
            )
            return False
            
    except requests.exceptions.Timeout:
        logger.debug(f"{service_name} health check timed out")
        return False
    except requests.exceptions.ConnectionError:
        logger.debug(f"{service_name} health check connection error")
        return False
    except Exception as e:
        logger.debug(f"{service_name} health check error: {str(e)}")
        return False


def wait_for_condition(
    condition: Callable[[], bool],
    timeout: int = 30,
    interval: float = 1.0,
    description: str = "condition"
) -> bool:
    """
    Wait for a condition to become true within a timeout period.
    
    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        description: Description of the condition (for logging)
        
    Returns:
        bool: True if condition was met, False if timeout occurred
        
    Example:
        >>> wait_for_condition(
        ...     lambda: requests.get(url).status_code == 200,
        ...     timeout=30,
        ...     description="Service to be ready"
        ... )
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            if condition():
                elapsed = time.time() - start_time
                logger.debug(f"Condition '{description}' met after {elapsed:.2f}s")
                return True
        except Exception as e:
            logger.debug(f"Condition '{description}' check error: {str(e)}")
        
        time.sleep(interval)
    
    elapsed = time.time() - start_time
    logger.warning(f"Condition '{description}' not met after {elapsed:.2f}s timeout")
    return False


# ============================================================================
# Test Markers
# ============================================================================

def pytest_configure(config):
    """
    Register custom pytest markers.
    """
    config.addinivalue_line(
        "markers",
        "benchmark: mark test as a performance benchmark"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running (>10s)"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test"
    )


# ============================================================================
# Test Reporting
# ============================================================================

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook to add extra information to test reports.
    
    Captures test duration and outcome for better reporting.
    """
    outcome = yield
    report = outcome.get_result()
    
    # Add custom attributes to the report
    if report.when == "call":
        report.duration_ms = report.duration * 1000
        
        # Log test result
        if report.passed:
            logger.info(f"✓ {item.name} passed in {report.duration:.2f}s")
        elif report.failed:
            logger.error(f"✗ {item.name} failed in {report.duration:.2f}s")
        elif report.skipped:
            logger.info(f"⊘ {item.name} skipped")


@pytest.fixture(scope="function", autouse=True)
def test_timer(request):
    """
    Automatically time each test function.
    """
    start_time = time.time()
    
    yield
    
    duration = time.time() - start_time
    logger.info(f"Test {request.node.name} took {duration:.2f}s")


# ============================================================================
# Cleanup
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def cleanup_after_tests(request, docker_compose_logs):
    """
    Perform cleanup operations after all tests complete.
    """
    yield
    
    # Log summary after tests
    logger.info("=" * 80)
    logger.info("E2E Test Suite Completed")
    logger.info("=" * 80)
    
    # Log service status
    for service, logs in docker_compose_logs.items():
        if "Could not retrieve" in logs:
            logger.warning(f"Failed to retrieve logs for {service}")
        else:
            log_lines = len(logs.split('\n'))
            logger.info(f"{service}: {log_lines} log lines captured")


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def wait_for():
    """
    Provides the wait_for_condition helper function to tests.
    
    Returns:
        Callable: The wait_for_condition function
    """
    return wait_for_condition


@pytest.fixture
def make_request():
    """
    Provides a helper function for making HTTP requests with retries.
    
    Returns:
        Callable: Function that makes HTTP requests with retry logic
    """
    def _make_request(
        url: str,
        method: str = "GET",
        max_retries: int = 3,
        timeout: int = 10,
        **kwargs
    ):
        """
        Make an HTTP request with automatic retries.
        
        Args:
            url: URL to request
            method: HTTP method (GET, POST, etc.)
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
            **kwargs: Additional arguments passed to requests
            
        Returns:
            requests.Response: The HTTP response
            
        Raises:
            requests.exceptions.RequestException: If all retries fail
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=timeout,
                    **kwargs
                )
                return response
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    logger.debug(f"Retry {attempt + 1}/{max_retries} for {url}")
        
        raise last_exception
    
    return _make_request
