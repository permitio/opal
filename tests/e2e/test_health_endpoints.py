"""
End-to-end tests for health endpoints.

Validates that all health check endpoints respond correctly.
"""

import pytest

from tests.e2e.utils.http_client import http_get_with_retries


def test_server_health_endpoint_responds(opal_server_url):
    """Test that OPAL server health endpoint returns 200 OK."""
    url = f"{opal_server_url}/healthcheck"
    response = http_get_with_retries(url, max_attempts=10)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    # Verify response content
    data = response.json()
    assert "status" in data, "Response should contain 'status' field"
    assert data["status"] == "ok", f"Expected status 'ok', got '{data.get('status')}'"


def test_server_root_endpoint_responds(opal_server_url):
    """Test that OPAL server root endpoint returns 200 OK."""
    url = f"{opal_server_url}/"
    response = http_get_with_retries(url, max_attempts=10)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_client_readiness_endpoint_responds(opal_client_url):
    """Test that OPAL client readiness endpoint returns 200 OK."""
    url = f"{opal_client_url}/ready"
    response = http_get_with_retries(url, max_attempts=15, timeout=15)
    
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Client may not have loaded policies and data yet."
    )
    
    # Verify response content
    data = response.json()
    assert "status" in data, "Response should contain 'status' field"


def test_client_health_endpoint_responds(opal_client_url):
    """Test that OPAL client health endpoint returns 200 OK."""
    url = f"{opal_client_url}/healthcheck"
    response = http_get_with_retries(url, max_attempts=10)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_opa_health_endpoint_responds(opa_url):
    """Test that OPA health endpoint returns 200 OK."""
    url = f"{opa_url}/health"
    response = http_get_with_retries(url, max_attempts=10)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
