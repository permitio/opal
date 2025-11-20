import pytest
import requests


@pytest.mark.e2e
@pytest.mark.docker
def test_statistics_endpoint_availability(server_url, api_client):
    """Test that statistics endpoint is available (may return 501 if disabled)."""
    response = api_client(f"{server_url}/statistics")
    
    # Statistics might be disabled (501) or enabled (200)
    assert response.status_code in [200, 501], f"Unexpected status code: {response.status_code}"
    
    if response.status_code == 200:
        # If enabled, verify it returns valid JSON
        json_data = response.json()
        assert isinstance(json_data, dict), "Statistics should return a JSON object"
        
        # Check for expected fields in statistics response
        expected_fields = ["uptime", "version", "clients", "servers"]
        for field in expected_fields:
            assert field in json_data, f"Missing field '{field}' in statistics response"


@pytest.mark.e2e
@pytest.mark.docker
def test_brief_stats_endpoint(server_url, api_client):
    """Test the brief statistics endpoint (/stats)."""
    response = api_client(f"{server_url}/stats")
    
    # Brief stats might be disabled (501) or enabled (200)
    assert response.status_code in [200, 501], f"Unexpected status code: {response.status_code}"
    
    if response.status_code == 200:
        json_data = response.json()
        assert isinstance(json_data, dict), "Brief stats should return a JSON object"
        
        # Check for expected fields in brief stats
        expected_fields = ["uptime", "version", "client_count", "server_count"]
        for field in expected_fields:
            assert field in json_data, f"Missing field '{field}' in brief stats response"
        
        # Verify data types
        assert isinstance(json_data["client_count"], (int, float)), "client_count should be numeric"
        assert isinstance(json_data["server_count"], (int, float)), "server_count should be numeric"


@pytest.mark.e2e
@pytest.mark.docker
def test_client_server_connection_via_stats(server_url, api_client):
    """Test client-server connection by checking if server is running."""
    # First verify server is responding
    health_response = api_client(f"{server_url}/healthcheck")
    assert health_response.status_code == 200, "Server should be healthy"
    
    # Check stats to see server information
    stats_response = api_client(f"{server_url}/stats")
    
    if stats_response.status_code == 200:
        stats_data = stats_response.json()
        
        # Server should report at least 1 server instance (itself)
        assert stats_data["server_count"] >= 1, "Should have at least 1 server instance"
        
        # Version should be present and non-empty
        assert stats_data["version"], "Server version should be present"
        
        print(f"✓ Server running version: {stats_data['version']}")
        print(f"✓ Connected clients: {stats_data['client_count']}")
        print(f"✓ Server instances: {stats_data['server_count']}")
    else:
        # If stats are disabled, just verify server is responding
        print("✓ Statistics disabled, but server is responding to health checks")