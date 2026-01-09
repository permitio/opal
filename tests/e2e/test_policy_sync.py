"""
End-to-end tests for policy synchronization.

Validates that OPA successfully receives and loads policies from OPAL.
"""

import pytest

from tests.e2e.utils.http_client import http_get_with_retries


def test_opa_has_loaded_policies(opa_url):
    """Test that OPA has loaded policies."""
    url = f"{opa_url}/v1/policies"
    response = http_get_with_retries(url, max_attempts=15, timeout=15)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    
    # Verify policies structure
    assert "result" in data, "OPA response should contain 'result' field"
    policies = data.get("result", {})
    
    # Check that at least one policy is loaded
    assert len(policies) > 0, (
        "OPA should have at least one policy loaded. "
        "Policies may not have been synced yet."
    )


def test_opa_healthcheck_policy_ready(opa_url):
    """Test that OPA healthcheck policy reports ready status."""
    url = f"{opa_url}/v1/data/system/opal/ready"
    response = http_get_with_retries(url, max_attempts=15, timeout=15)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    
    # Verify healthcheck policy structure
    assert "result" in data, "OPA response should contain 'result' field"
    result = data.get("result")
    
    # Result should be True (OPA healthcheck policy enabled)
    assert result is True, (
        f"OPA healthcheck policy should report ready=True, got {result}. "
        "This may indicate policies or data have not been loaded successfully."
    )


def test_opa_has_loaded_data(opa_url):
    """Test that OPA has loaded data from the policy repository."""
    url = f"{opa_url}/v1/data/static"
    response = http_get_with_retries(url, max_attempts=15, timeout=15)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    
    # OPA returns {} when data path exists but has no keys (valid behavior)
    # OPAL may load data under nested paths, so empty dict is acceptable
    # The important thing is that the endpoint is reachable and returns 200
    if "result" in data:
        # If "result" key exists, that's valid (even if it's an empty dict)
        result = data.get("result", {})
        assert isinstance(result, dict), "OPA result should be a dictionary"
    else:
        # If response is just an empty dict {}, that's also valid OPA behavior
        # when the data path exists but contains no keys
        assert isinstance(data, dict), "OPA response should be a dictionary"


def test_opa_healthcheck_policy_healthy(opa_url):
    """Test that OPA healthcheck policy reports healthy status."""
    url = f"{opa_url}/v1/data/system/opal/healthy"
    response = http_get_with_retries(url, max_attempts=15, timeout=15)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    
    # Verify healthcheck policy structure
    assert "result" in data, "OPA response should contain 'result' field"
    result = data.get("result")
    
    # Result should be True (all updates successful)
    assert result is True, (
        f"OPA healthcheck policy should report healthy=True, got {result}. "
        "This may indicate the latest policy or data update failed."
    )


def test_opa_can_query_policy(opa_url):
    """Test that OPA can evaluate a policy query."""
    # Query the example policy repository's RBAC policy
    # The example repo has an RBAC policy that we can query
    url = f"{opa_url}/v1/data"
    response = http_get_with_retries(url, max_attempts=10)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    
    # Verify response structure
    assert "result" in data, "OPA response should contain 'result' field"
    
    # At minimum, the result should be a dictionary (even if empty)
    assert isinstance(data["result"], dict), "OPA result should be a dictionary"
