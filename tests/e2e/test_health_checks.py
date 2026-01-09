import pytest


@pytest.mark.e2e
class TestHealthChecks:
    """Tests for OPAL health check endpoints."""

    def test_server_healthcheck(self, server_client):
        """Verify server /healthcheck returns ok status."""
        response = server_client.get("/healthcheck")
        assert response.status_code == 200, f"Server healthcheck failed with status {response.status_code}"
        assert response.json() == {"status": "ok"}, f"Unexpected response: {response.json()}"

    def test_server_root_endpoint(self, server_client):
        """Verify server root endpoint returns ok status."""
        response = server_client.get("/")
        assert response.status_code == 200, f"Server root endpoint failed with status {response.status_code}"
        assert response.json() == {"status": "ok"}, f"Unexpected response: {response.json()}"

    def test_client_healthcheck(self, client_client):
        """Verify client /healthcheck returns ok status."""
        response = client_client.get("/healthcheck")
        assert response.status_code == 200, f"Client healthcheck failed with status {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok", f"Unexpected status: {data}"

    def test_client_root_endpoint(self, client_client):
        """Verify client root endpoint returns ok status."""
        response = client_client.get("/")
        assert response.status_code == 200, f"Client root endpoint failed with status {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok", f"Unexpected status: {data}"

    def test_client_healthy_endpoint(self, client_client, wait_for_condition):
        """Verify client /healthy endpoint shows online status."""
        def check_healthy():
            try:
                response = client_client.get("/healthy")
                if response.status_code != 200:
                    return False
                data = response.json()
                return data.get("status") == "ok" and data.get("online") is True
            except Exception:
                return False

        success = wait_for_condition(
            check_healthy,
            timeout=45,
            interval=2,
            error_message="Client did not become healthy within timeout"
        )

        assert success, "Client /healthy endpoint did not return expected status"

    def test_client_ready_endpoint(self, client_client, wait_for_condition):
        """Verify client /ready endpoint returns 200."""
        def check_ready():
            try:
                response = client_client.get("/ready")
                return response.status_code == 200
            except Exception:
                return False

        success = wait_for_condition(
            check_ready,
            timeout=45,
            interval=2,
            error_message="Client did not become ready within timeout"
        )

        assert success, "Client /ready endpoint did not return 200"

    @pytest.mark.parametrize("endpoint", [
        "/healthcheck",
        "/",
    ])
    def test_server_health_endpoints_accessible(self, server_client, endpoint):
        """Verify all server health endpoints are accessible."""
        response = server_client.get(endpoint)
        assert response.status_code == 200, f"Endpoint {endpoint} returned {response.status_code}"

    @pytest.mark.parametrize("endpoint", [
        "/healthcheck",
        "/",
        "/healthy",
        "/ready",
    ])
    def test_client_health_endpoints_accessible(self, client_client, endpoint):
        """Verify all client health endpoints are accessible."""
        response = client_client.get(endpoint)
        assert response.status_code in [200, 503], \
            f"Endpoint {endpoint} returned unexpected status {response.status_code}"
