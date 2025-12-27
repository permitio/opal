import requests
import time

def test_opal_server_health(opal_server_url):
    """Test that the OPAL server is healthy."""
    response = requests.get(f"{opal_server_url}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_opal_client_health(opal_client_url):
    """Test that the OPAL client is healthy."""
    response = requests.get(f"{opal_client_url}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_opa_health(opa_url):
    """Test that OPA is healthy (via OPAL client)."""
    response = requests.get(f"{opa_url}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_opal_client_server_connection(opal_client_url):
    """Test that the OPAL client is connected to the server and receives updates."""
    # It might take a moment for the client to connect and receive initial data.
    # We'll poll the statistics endpoint until we see a connected status or a timeout.
    timeout = 30
    start_time = time.time()
    connected = False
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{opal_client_url}/statistics")
            if response.status_code == 200:
                data = response.json()
                # Assuming the statistics endpoint provides some indication of connection
                # and successful policy/data updates. This might need refinement
                # based on the actual statistics API response structure.
                if data.get("client_is_connected", False) and data.get("last_policy_update", None) is not None:
                    connected = True
                    break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    assert connected, "OPAL client did not connect to the server or receive updates within the timeout."
