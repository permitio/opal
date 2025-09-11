import requests
import time
import subprocess

def check_logs(container_name):
    result = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
    assert "ERROR" not in result.stdout and "CRITICAL" not in result.stdout, f"Critical errors found in {container_name}"

def test_opal_server_health():
    """Test OPAL Server health endpoint."""
    response = requests.get("http://opal_server:7002/healthcheck")
    assert response.status_code == 200

def test_opal_client_health():
    """Test OPAL Client endpoint."""
    response = requests.get("http://opal_client:7000/healthcheck")
    assert response.status_code == 200
    print(response.json())    

def test_opal_server_logs():
    check_logs("app-tests-opal_server-1")

def test_opal_client_logs():
    check_logs("app-tests-opal_client-1")
