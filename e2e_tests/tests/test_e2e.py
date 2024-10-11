import requests
import time

def test_opal_server_health():
    """Test OPAL Server health endpoint."""
    response = requests.get("http://localhost:7002/healthcheck")
    assert response.status_code == 200

def test_opal_client_health():
    """Test OPAL Client endpoint."""

    response = requests.get("http://localhost:7000/healthcheck")
    assert response.status_code == 200
    print(response.json())    