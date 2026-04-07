import pytest
import requests


@pytest.mark.e2e
@pytest.mark.docker
def test_server_healthcheck_endpoint(server_url, api_client):
    """Test that OPAL server /healthcheck endpoint returns 200 OK."""
    response = api_client(f"{server_url}/healthcheck")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    # Verify response content
    json_data = response.json()
    assert json_data == {"status": "ok"}, f"Expected {{'status': 'ok'}}, got {json_data}"


@pytest.mark.e2e
@pytest.mark.docker
def test_server_root_endpoint(server_url, api_client):
    """Test that OPAL server root endpoint (/) returns 200 OK."""
    response = api_client(f"{server_url}/")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    # Verify response content
    json_data = response.json()
    assert json_data == {"status": "ok"}, f"Expected {{'status': 'ok'}}, got {json_data}"


@pytest.mark.e2e
@pytest.mark.docker
def test_server_responds_quickly(server_url, api_client):
    """Test that server responds within reasonable time."""
    import time
    
    start_time = time.time()
    response = api_client(f"{server_url}/healthcheck")
    response_time = time.time() - start_time
    
    assert response.status_code == 200
    assert response_time < 5.0, f"Server took too long to respond: {response_time:.2f}s"