"""
Simplified PyTest Configuration for OPAL E2E Tests

Assumes Docker images are already built via `make test-e2e`.
"""

import pytest
import requests
import time
import logging
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# Docker Compose Management
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def docker_compose_services():
    """
    Manage docker-compose lifecycle for the test session.
    Assumes images are already built via Makefile.
    """
    compose_file = Path(__file__).parent / "docker-compose.yml"
    project_name = "opal_e2e_tests"
    
    logger.info("=" * 80)
    logger.info("OPAL E2E Tests - Docker Setup")
    logger.info("=" * 80)
    
    # Check if required images exist
    logger.info("Checking for required Docker images...")
    required_images = ["opal-server-local:latest", "opal-client-local:latest"]
    for image in required_images:
        result = subprocess.run(
            ["docker", "images", "-q", image],
            capture_output=True,
            text=True
        )
        if not result.stdout.strip():
            logger.error(f"Required image not found: {image}")
            logger.error("Please build images first using: make test-e2e")
            pytest.exit(f"Missing Docker image: {image}", returncode=1)
    
    logger.info("✓ All required images found")
    
    # Check for port conflicts before starting
    logger.info("Checking for port conflicts...")
    ports_to_check = [7002, 7766, 8181, 5432]
    for port in ports_to_check:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}:{{.Ports}}"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            logger.warning(f"Port {port} is already in use by: {result.stdout.strip()}")
            logger.warning("This might cause conflicts. Consider stopping the container using this port.")
    
    # Clean up any existing containers
    logger.info("Cleaning up old containers...")
    cleanup_result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "-p", project_name, "down", "-v"],
        capture_output=True,
        text=True,
        cwd=compose_file.parent
    )
    if cleanup_result.returncode != 0:
        logger.warning(f"Cleanup had issues (non-fatal): {cleanup_result.stderr}")
    
    # Start services
    logger.info("Starting Docker Compose services...")
    start_result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "-p", project_name, "up", "-d"],
        capture_output=True,
        text=True,
        cwd=compose_file.parent
    )
    
    if start_result.returncode != 0:
        logger.error("=" * 80)
        logger.error("CRITICAL: Docker Compose failed to start services!")
        logger.error("=" * 80)
        logger.error(f"Command: docker compose -f {compose_file} -p {project_name} up -d")
        logger.error(f"Exit code: {start_result.returncode}")
        if start_result.stdout:
            logger.error(f"STDOUT:\n{start_result.stdout}")
        if start_result.stderr:
            logger.error(f"STDERR:\n{start_result.stderr}")
        
        # Try to get more info about what failed
        ps_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "-p", project_name, "ps", "-a"],
            capture_output=True,
            text=True,
            cwd=compose_file.parent
        )
        if ps_result.stdout.strip():
            logger.error(f"Container status:\n{ps_result.stdout}")
        
        # Cleanup before exiting
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "-p", project_name, "down", "-v"],
            capture_output=True,
            cwd=compose_file.parent
        )
        
        error_msg = f"Docker Compose failed to start services. Check logs above for details. Exit code: {start_result.returncode}"
        pytest.exit(error_msg, returncode=1)
    
    logger.info("✓ Services started")
    
    # Wait for services to be ready
    logger.info("Waiting for services to be ready...")
    logger.info("Initial wait: 15 seconds to allow containers to fully start and port mappings to be established")
    time.sleep(15)  # Initial stabilization - increased to allow containers to fully start
    
    # First, wait for containers to be running
    logger.info("Waiting for containers to be in running state...")
    container_services = ["opal_server", "opal_client", "broadcast_channel"]
    for service in container_services:
        container_ready = False
        container_check_start = time.time()
        while time.time() - container_check_start < 60:  # Wait up to 60s for containers
            ps_result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "-p", project_name, "ps", "-q", service],
                capture_output=True,
                text=True,
                cwd=compose_file.parent
            )
            if ps_result.stdout.strip():
                container_ids = ps_result.stdout.strip().split('\n')
                for container_id in container_ids:
                    if container_id.strip():
                        inspect_result = subprocess.run(
                            ["docker", "inspect", "-f", "{{.State.Status}}", container_id.strip()],
                            capture_output=True,
                            text=True
                        )
                        if inspect_result.stdout.strip() == "running":
                            logger.info(f"✓ Container {service} is running")
                            container_ready = True
                            break
                if container_ready:
                    break
            time.sleep(1)
        if not container_ready:
            logger.warning(f"Container {service} did not start within 60s, continuing anyway...")
    
    # Define services with their health check URLs
    services_ready = {
        "OPAL Server": "http://localhost:7002/",
        "OPAL Client": "http://localhost:7766/healthcheck",
        "OPA": "http://localhost:8181/health"
    }
    
    max_wait = 300  # 5 minutes total - increased for slower Windows environments
    start_time = time.time()
    
    for service_name, url in services_ready.items():
        logger.info(f"Checking {service_name} at {url}...")
        ready = False
        service_start = time.time()
        last_error = None
        
        while time.time() - start_time < max_wait:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    elapsed = time.time() - service_start
                    logger.info(f"✓ {service_name} is ready (took {elapsed:.1f}s)")
                    ready = True
                    break
            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)}"
                # Log connection errors periodically for debugging
                elapsed_check = time.time() - service_start
                if int(elapsed_check) % 10 == 0 and int(elapsed_check) > 0:  # Log every 10 seconds
                    logger.info(f"Still waiting for {service_name} at {url} (elapsed: {elapsed_check:.1f}s): {last_error}")
                    # Also check container status periodically
                    try:
                        ps_result = subprocess.run(
                            ["docker", "compose", "-f", str(compose_file), "-p", project_name, "ps"],
                            capture_output=True,
                            text=True,
                            cwd=compose_file.parent
                        )
                        if ps_result.stdout.strip():
                            logger.debug(f"Container status:\n{ps_result.stdout}")
                    except:
                        pass
            time.sleep(2)
        
        if not ready:
            elapsed = time.time() - start_time
            logger.error(f"✗ {service_name} failed to become ready after {elapsed:.1f}s")
            if last_error:
                logger.error(f"Last error: {last_error}")
            
            # Show container status
            ps_result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "-p", project_name, "ps"],
                capture_output=True,
                text=True,
                cwd=compose_file.parent
            )
            logger.error(f"Container status:\n{ps_result.stdout}")
            
            # Show logs
            log_result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "-p", project_name, "logs", "--tail=50"],
                capture_output=True,
                text=True,
                cwd=compose_file.parent
            )
            logger.error(f"Container logs:\n{log_result.stdout}")
            
            # Check for specific container issues
            if service_name == "OPAL Client":
                # Check if the client container is running but not responding
                client_logs = subprocess.run(
                    ["docker", "compose", "-f", str(compose_file), "-p", project_name, "logs", "opal_client", "--tail=100"],
                    capture_output=True,
                    text=True,
                    cwd=compose_file.parent
                )
                logger.error(f"OPAL Client specific logs:\n{client_logs.stdout}")
                
                # Check if port is in use
                port_check = subprocess.run(
                    ["docker", "ps", "--filter", "publish=7766", "--format", "{{.Names}}:{{.Ports}}"],
                    capture_output=True,
                    text=True
                )
                if port_check.stdout.strip():
                    logger.warning(f"Port 7766 is already in use: {port_check.stdout.strip()}")
            
            # Cleanup
            subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "-p", project_name, "down", "-v"],
                capture_output=True,
                cwd=compose_file.parent
            )
            
            error_msg = f"{service_name} failed to become ready after {elapsed:.1f}s. Check logs above for details."
            logger.error(f"ERROR: {error_msg}")
            pytest.exit(error_msg, returncode=1)
    
    total_time = time.time() - start_time
    logger.info(f"✓ All services ready! (total time: {total_time:.1f}s)")
    logger.info("=" * 80)
    
    yield
    
    # Cleanup after tests
    logger.info("=" * 80)
    logger.info("Cleaning up Docker Compose services...")
    
    # Capture logs before stopping
    log_result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "-p", project_name, "logs"],
        capture_output=True,
        text=True,
        cwd=compose_file.parent
    )
    
    # Save logs to file
    log_file = Path(__file__).parent / "test_logs.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(log_result.stdout)
    logger.info(f"✓ Logs saved to {log_file}")
    
    # Stop and remove everything
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "-p", project_name, "down", "-v"],
        capture_output=True,
        cwd=compose_file.parent
    )
    
    logger.info("✓ Cleanup complete")
    logger.info("=" * 80)


# ============================================================================
# Service URL Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def opal_server_url():
    """OPAL Server base URL"""
    return "http://localhost:7002"


@pytest.fixture(scope="session")
def opal_client_url():
    """OPAL Client base URL"""
    return "http://localhost:7766"


@pytest.fixture(scope="session")
def opa_url():
    """OPA base URL"""
    return "http://localhost:8181"


# ============================================================================
# Helper Functions
# ============================================================================

def is_service_healthy(url: str, timeout: int = 10) -> bool:
    """Check if a service is healthy."""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except:
        return False


def wait_for_condition(condition, timeout: int = 30, interval: float = 1.0, description: str = "condition") -> bool:
    """Wait for a condition to become true."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            if condition():
                return True
        except:
            pass
        time.sleep(interval)
    
    return False


# ============================================================================
# Test Markers
# ============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "benchmark: mark test as a performance benchmark")
    config.addinivalue_line("markers", "slow: mark test as slow running (>10s)")
    config.addinivalue_line("markers", "integration: mark test as integration test")


# ============================================================================
# Test Reporting
# ============================================================================

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to add extra information to test reports."""
    outcome = yield
    report = outcome.get_result()
    
    if report.when == "call":
        if report.passed:
            logger.info(f"✓ {item.name} passed")
        elif report.failed:
            logger.error(f"✗ {item.name} failed")
        elif report.skipped:
            logger.info(f"⊘ {item.name} skipped")


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def wait_for():
    """Provides the wait_for_condition helper function to tests."""
    return wait_for_condition


@pytest.fixture
def make_request():
    """Provides a helper function for making HTTP requests with retries."""
    def _make_request(url: str, method: str = "GET", max_retries: int = 3, timeout: int = 10, **kwargs):
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = requests.request(method, url, timeout=timeout, **kwargs)
                return response
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
        
        raise last_exception
    
    return _make_request


@pytest.fixture(scope="session")
def docker_compose_logs():
    """Retrieve logs from all Docker Compose services."""
    compose_file = Path(__file__).parent / "docker-compose.yml"
    project_name = "opal_e2e_tests"
    
    # Get list of running services
    ps_result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "-p", project_name, "ps", "-q"],
        capture_output=True,
        text=True,
        cwd=compose_file.parent
    )
    
    if ps_result.returncode != 0:
        logger.warning("Could not list Docker Compose services")
        return {}
    
    container_ids = ps_result.stdout.strip().split('\n')
    logs_dict = {}
    
    # Define service names
    services = ["opal_server", "opal_client", "broadcast_channel"]
    
    for service in services:
        log_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "-p", project_name, "logs", service],
            capture_output=True,
            text=True,
            cwd=compose_file.parent,
            timeout=10
        )
        
        if log_result.returncode == 0:
            logs_dict[service] = log_result.stdout
        else:
            logs_dict[service] = f"Could not retrieve logs for {service}"
    
    return logs_dict
