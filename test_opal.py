import requests
import time
import pytest
import subprocess


def wait_for_any_health(port, paths, name, timeout_seconds=180):
    print(f"Waiting for {name} on port {port}...")
    start = time.time()
    session = requests.Session()
    last_error = None
    while time.time() - start < timeout_seconds:
        for path in paths:
            try:
                r = session.get(f"http://localhost:{port}{path}", timeout=3)
                if r.status_code == 200:
                    print(f"✅ {name} is ready on {path}")
                    return True
            except Exception as exc:
                last_error = exc
        time.sleep(2)
    if last_error:
        print(f"Last error for {name}: {last_error}")
    return False


def wait_for_statistics_connected(port, timeout_seconds=240):
    print("Checking if client is connected...")
    start = time.time()
    session = requests.Session()
    while time.time() - start < timeout_seconds:
        try:
            r = session.get(f"http://localhost:{port}/statistics", timeout=4)
            if r.status_code == 200:
                data = r.json()
                if data.get("client_is_connected") is True:
                    print("✅ Client connected to server")
                    return True
                connected_clients = data.get("connected_clients") or data.get("clients")
                if isinstance(connected_clients, list) and len(connected_clients) > 0:
                    print("✅ Client connected to server")
                    return True
                if isinstance(connected_clients, dict) and len(connected_clients.keys()) > 0:
                    print("✅ Client connected to server")
                    return True
                if isinstance(connected_clients, int) and connected_clients > 0:
                    print("✅ Client connected to server")
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def test_check_health():
    server_paths = ["/healthcheck", "/", "/healthz", "/ready"]
    client_paths = ["/healthcheck", "/healthy", "/", "/ready"]
    assert wait_for_any_health(7002, server_paths, "OPAL Server")
    assert wait_for_any_health(7000, client_paths, "OPAL Client")


def test_check_connection():
    if not wait_for_statistics_connected(7002):
        pytest.fail("❌ Client never connected to server")


def test_check_logs():
    print("Checking logs for CRITICAL errors...")
    logs = subprocess.check_output(
        ["docker", "compose", "logs"],
        stderr=subprocess.STDOUT
    ).decode()

    assert "CRITICAL" not in logs
    print("✅ Logs are clean")
