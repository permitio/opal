import subprocess
import time
import requests
import signal
import os


SERVER_URL = "http://127.0.0.1:7002"


def start_server():
    process = subprocess.Popen(
        [
            "uvicorn",
            "opal_server.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "7002",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )

    # wait for server to be ready
    for _ in range(10):
        try:
            requests.get(f"{SERVER_URL}/healthcheck", timeout=1)
            return process
        except Exception:
            time.sleep(1)

    raise RuntimeError("Server did not start")


def stop_server(process):
    process.send_signal(signal.SIGINT)
    process.wait(timeout=5)


def test_server_healthcheck_e2e():
    process = start_server()

    try:
        response = requests.get(f"{SERVER_URL}/healthcheck")
        assert response.status_code == 200
    finally:
        stop_server(process)
