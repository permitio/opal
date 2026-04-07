import pytest


@pytest.mark.e2e
class TestStatistics:
    """Tests for OPAL statistics API."""

    def test_server_statistics_enabled(self, server_client):
        """Verify statistics are enabled and accessible on server."""
        response = server_client.get("/statistics")

        assert response.status_code == 200, \
            f"Statistics endpoint returned {response.status_code}. " \
            f"Ensure OPAL_STATISTICS_ENABLED=true is set"

        data = response.json()
        assert "clients" in data, "Statistics response missing 'clients' field"
        assert "uptime" in data, "Statistics response missing 'uptime' field"
        assert "version" in data, "Statistics response missing 'version' field"

    def test_server_stats_brief(self, server_client):
        """Verify brief stats endpoint returns expected fields."""
        response = server_client.get("/stats")

        assert response.status_code == 200, \
            f"Brief stats endpoint returned {response.status_code}"

        data = response.json()
        assert "client_count" in data, "Stats response missing 'client_count' field"
        assert "uptime" in data, "Stats response missing 'uptime' field"
        assert "version" in data, "Stats response missing 'version' field"

        assert isinstance(data["client_count"], int), \
            f"client_count should be int, got {type(data['client_count'])}"

    def test_client_connected_to_server(self, server_client, wait_for_condition):
        """Verify client is registered in server statistics."""
        def check_client_connected():
            try:
                response = server_client.get("/stats")
                if response.status_code != 200:
                    return False

                data = response.json()
                client_count = data.get("client_count", 0)

                return client_count > 0

            except Exception as e:
                print(f"Error checking client connection: {e}")
                return False

        success = wait_for_condition(
            check_client_connected,
            timeout=60,
            interval=3,
            error_message="Client did not connect to server within timeout"
        )

        assert success, "Client did not appear in server statistics"

        response = server_client.get("/stats")
        data = response.json()
        assert data["client_count"] >= 1, \
            f"Expected at least 1 client, found {data['client_count']}"

    def test_statistics_detailed_client_info(self, server_client, wait_for_condition):
        """Verify detailed statistics contain client information."""
        def check_detailed_stats():
            try:
                response = server_client.get("/statistics")
                if response.status_code != 200:
                    return False

                data = response.json()
                clients = data.get("clients", {})

                return len(clients) > 0

            except Exception:
                return False

        success = wait_for_condition(
            check_detailed_stats,
            timeout=60,
            interval=3,
            error_message="No client details found in statistics"
        )

        assert success, "Detailed statistics did not contain client information"

        response = server_client.get("/statistics")
        data = response.json()
        clients = data.get("clients", {})

        assert len(clients) >= 1, \
            f"Expected at least 1 client in detailed stats, found {len(clients)}"

    def test_statistics_counts_match(self, server_client, wait_for_condition):
        """Verify client_count in brief stats matches detailed statistics."""
        def check_counts_match():
            try:
                stats_response = server_client.get("/stats")
                detailed_response = server_client.get("/statistics")

                if stats_response.status_code != 200 or detailed_response.status_code != 200:
                    return False

                brief_count = stats_response.json().get("client_count", 0)
                detailed_count = len(detailed_response.json().get("clients", {}))

                return brief_count > 0 and brief_count == detailed_count

            except Exception:
                return False

        success = wait_for_condition(
            check_counts_match,
            timeout=60,
            interval=3,
            error_message="Client counts did not match between brief and detailed stats"
        )

        assert success, "Brief and detailed statistics client counts do not match"
