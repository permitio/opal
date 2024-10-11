import requests

def test_opal_server_health():
    """Test OPAL Server health endpoint."""
    response = requests.get("http://localhost:7002/policy-data")
    assert response.status_code == 200

def test_opal_client_health():
    """Test OPAL Client endpoint."""
    response = requests.get("http://localhost:7766/ready")
    assert response.status_code == 200
    assert 'connected' in response.json()
