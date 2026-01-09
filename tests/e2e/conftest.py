"""
Pytest configuration and fixtures for OPAL end-to-end tests.

This module provides session-scoped fixtures to manage the Docker Compose
lifecycle for E2E tests. Containers are started once per test session and
torn down after all tests complete.
"""

import json
import subprocess
import time
from typing import Dict, List

import pytest

from tests.e2e.utils.docker_compose import get_compose_file_path, get_compose_services, run_compose_command

# Path to the E2E Docker Compose file
COMPOSE_FILE = get_compose_file_path()

# Maximum time to wait for services to become healthy (in seconds)
HEALTH_CHECK_TIMEOUT = 120

# Interval between health check attempts (in seconds)
HEALTH_CHECK_INTERVAL = 2


def run_docker_compose_command(command: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a docker compose command and return the result.
    
    Args:
        command: List of command arguments (without 'docker compose')
        check: If True, raise CalledProcessError on non-zero exit
        
    Returns:
        CompletedProcess with stdout and stderr
        
    Raises:
        subprocess.CalledProcessError: If command fails and check=True
    """
    return run_compose_command(command, check=check)


def get_service_status() -> Dict[str, str]:
    """
    Get the health status of all services.
    
    Returns:
        Dictionary mapping service names to their status
        (e.g., {"opal_server": "healthy", "opal_client": "starting"})
    """
    result = run_docker_compose_command(["ps", "--format", "json"], check=False)
    
    if result.returncode != 0:
        return {}
    
    services = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            service_info = json.loads(line)
            service_name = service_info.get("Service", "")
            health = service_info.get("Health", "")
            # Normalize health status
            if health:
                services[service_name] = health.lower()
            else:
                # If no health check, use state
                state = service_info.get("State", "unknown").lower()
                services[service_name] = state
        except (json.JSONDecodeError, KeyError):
            continue
    
    return services


def wait_for_services_healthy(timeout: int = HEALTH_CHECK_TIMEOUT) -> None:
    """
    Wait for all services to become healthy.
    
    Polls Docker Compose health status and waits for services to transition
    from "starting" or "unhealthy" to "healthy" or "running". Does not fail
    immediately on "unhealthy" status - instead continues polling until timeout.
    
    Args:
        timeout: Maximum time to wait in seconds
        
    Raises:
        RuntimeError: If services don't become healthy within timeout
    """
    start_time = time.time()
    last_status = {}
    expected_services = []
    last_log_time = 0
    log_interval = 10  # Log status every 10 seconds
    
    while time.time() - start_time < timeout:
        status = get_service_status()
        last_status = status
        
        # Get list of expected services from Docker Compose
        if not expected_services:
            expected_services = get_compose_services()
            if not expected_services:
                # Services not started yet, wait and retry
                time.sleep(HEALTH_CHECK_INTERVAL)
                continue
        
        # Check if all expected services are healthy
        all_healthy = True
        unhealthy_services = []
        
        for service in expected_services:
            service_status = status.get(service, "unknown")
            # Accept "healthy" or "running" as valid states
            # "starting" and "unhealthy" are intermediate states - keep polling
            if service_status not in ("healthy", "running"):
                all_healthy = False
                unhealthy_services.append((service, service_status))
        
        if all_healthy:
            elapsed = time.time() - start_time
            print(f"[E2E Setup] All services healthy after {elapsed:.1f}s")
            return
        
        # Log progress periodically (not on every iteration to avoid spam)
        elapsed = time.time() - start_time
        if elapsed - last_log_time >= log_interval:
            status_summary = ", ".join(
                f"{svc}: {stat}" for svc, stat in unhealthy_services
            )
            print(
                f"[E2E Setup] Waiting for services... ({elapsed:.0f}s/{timeout}s) - {status_summary}"
            )
            last_log_time = elapsed
        
        time.sleep(HEALTH_CHECK_INTERVAL)
    
    # Timeout reached - provide detailed error message
    elapsed = time.time() - start_time
    error_msg = (
        f"Services did not become healthy within {timeout} seconds (waited {elapsed:.1f}s).\n"
        f"Final status:\n"
    )
    for service in expected_services if expected_services else last_status.keys():
        status = last_status.get(service, "not found")
        error_msg += f"  - {service}: {status}\n"
    
    error_msg += "\nContainer logs (last 2000 chars):\n"
    try:
        logs_result = run_docker_compose_command(["logs"], check=False)
        error_msg += logs_result.stdout[-2000:]  # Last 2000 chars
    except Exception:
        error_msg += "  (Could not retrieve logs)\n"
    
    raise RuntimeError(error_msg)


@pytest.fixture(scope="session")
def docker_compose_stack():
    """
    Session-scoped fixture that manages the Docker Compose lifecycle.
    
    Starts all services once per test session, waits for them to be healthy,
    and tears them down after all tests complete.
    
    Yields:
        None: Fixture yields control to tests after services are healthy
        
    Raises:
        RuntimeError: If services fail to start or become healthy
    """
    # Ensure compose file exists
    if not COMPOSE_FILE.exists():
        raise FileNotFoundError(
            f"Docker Compose file not found: {COMPOSE_FILE}\n"
            f"Expected path: {COMPOSE_FILE.absolute()}"
        )
    
    # Stop any existing containers from previous runs
    print("\n[E2E Setup] Cleaning up any existing containers...")
    run_docker_compose_command(["down", "-v"], check=False)
    
    # Start services
    print(f"[E2E Setup] Starting Docker Compose stack from {COMPOSE_FILE}...")
    try:
        result = run_docker_compose_command(["up", "-d"], check=True)
        print("[E2E Setup] Containers started successfully")
    except subprocess.CalledProcessError as e:
        error_msg = (
            f"Failed to start Docker Compose stack.\n"
            f"Command: {' '.join(e.cmd)}\n"
            f"Return code: {e.returncode}\n"
            f"Stdout: {e.stdout}\n"
            f"Stderr: {e.stderr}"
        )
        raise RuntimeError(error_msg) from e
    
    # Wait for services to become healthy
    print("[E2E Setup] Waiting for services to become healthy...")
    try:
        wait_for_services_healthy()
        print("[E2E Setup] All services are healthy. Tests can begin.")
    except RuntimeError as e:
        # Clean up on failure
        print("\n[E2E Setup] Health check failed. Cleaning up...")
        run_docker_compose_command(["down", "-v"], check=False)
        raise
    
    # Yield control to tests
    yield
    
    # Teardown: Stop and remove containers
    print("\n[E2E Teardown] Stopping Docker Compose stack...")
    try:
        run_docker_compose_command(["down", "-v"], check=False)
        print("[E2E Teardown] Containers stopped and removed")
    except Exception as e:
        print(f"[E2E Teardown] Warning: Error during cleanup: {e}")


@pytest.fixture(scope="session")
def opal_server_url(docker_compose_stack):
    """
    URL of the OPAL server for E2E tests.
    
    Returns:
        str: Base URL of the OPAL server (e.g., "http://localhost:17002")
    """
    return "http://localhost:17002"


@pytest.fixture(scope="session")
def opal_client_url(docker_compose_stack):
    """
    URL of the OPAL client for E2E tests.
    
    Returns:
        str: Base URL of the OPAL client (e.g., "http://localhost:17766")
    """
    return "http://localhost:17766"


@pytest.fixture(scope="session")
def opa_url(docker_compose_stack):
    """
    URL of the OPA instance for E2E tests.
    
    Returns:
        str: Base URL of OPA (e.g., "http://localhost:18181")
    """
    return "http://localhost:18181"
