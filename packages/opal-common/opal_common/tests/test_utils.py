import time

import requests


def wait_for_server(port: int, timeout: int = 2):
    """Waits for the http server (of either the server or the client) to be
    available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            # Assumes both server and client have "/" route
            requests.get(f"http://localhost:{port}/")
            return
        except requests.exceptions.ConnectionError:
            time.sleep(0.1)
    raise TimeoutError(f"Server did not start within {timeout} seconds")
