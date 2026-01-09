import pytest


@pytest.mark.e2e
class TestConnectivity:
    """Tests for client-server connectivity."""

    def test_client_connects_to_server_via_logs(self, client_logs, wait_for_condition):
        """Verify client logs show successful connection to server."""
        def check_connection_in_logs():
            try:
                logs = client_logs.get_all(refresh=True)
                logs_lower = logs.lower()

                connection_indicators = [
                    "connected",
                    "websocket",
                    "pubsub",
                    "subscription"
                ]

                return any(indicator in logs_lower for indicator in connection_indicators)

            except Exception as e:
                print(f"Error checking logs: {e}")
                return False

        success = wait_for_condition(
            check_connection_in_logs,
            timeout=45,
            interval=2,
            error_message="Client connection indicators not found in logs"
        )

        assert success, "Client did not log successful connection to server"

    def test_client_receives_initial_policy(self, client_logs, wait_for_condition):
        """Verify client receives policy bundle on startup."""
        def check_policy_received():
            try:
                logs = client_logs.get_all(refresh=True)
                logs_lower = logs.lower()

                policy_indicators = [
                    "policy",
                    "bundle",
                    "rego"
                ]

                return any(indicator in logs_lower for indicator in policy_indicators)

            except Exception as e:
                print(f"Error checking logs: {e}")
                return False

        success = wait_for_condition(
            check_policy_received,
            timeout=60,
            interval=2,
            error_message="Client did not receive policy bundle within timeout"
        )

        assert success, "Client did not log policy bundle reception"

    def test_statistics_confirm_connection(self, server_client, wait_for_condition):
        """Verify server statistics confirm client connection."""
        def check_stats():
            try:
                response = server_client.get("/stats")
                if response.status_code != 200:
                    return False

                data = response.json()
                return data.get("client_count", 0) >= 1

            except Exception:
                return False

        success = wait_for_condition(
            check_stats,
            timeout=60,
            interval=3,
            error_message="Server statistics did not show connected client"
        )

        assert success, "Server statistics do not confirm client connection"

    def test_server_logs_show_client_connection(self, server_logs, wait_for_condition):
        """Verify server logs show client connection."""
        def check_server_logs():
            try:
                logs = server_logs.get_all(refresh=True)
                logs_lower = logs.lower()

                connection_indicators = [
                    "client",
                    "connected",
                    "websocket",
                    "subscription"
                ]

                return any(indicator in logs_lower for indicator in connection_indicators)

            except Exception as e:
                print(f"Error checking server logs: {e}")
                return False

        success = wait_for_condition(
            check_server_logs,
            timeout=45,
            interval=2,
            error_message="Server did not log client connection"
        )

        assert success, "Server logs do not show client connection"

    def test_opa_is_accessible(self, opa_client):
        """Verify OPA is accessible and responding."""
        response = opa_client.get("/health")

        assert response.status_code == 200, \
            f"OPA health check failed with status {response.status_code}"

    def test_opa_has_policies(self, opa_client, wait_for_condition):
        """Verify OPA has received policies from OPAL client."""
        def check_opa_policies():
            try:
                response = opa_client.get("/v1/policies")
                if response.status_code != 200:
                    return False

                policies = response.json().get("result", [])
                return len(policies) > 0

            except Exception:
                return False

        success = wait_for_condition(
            check_opa_policies,
            timeout=60,
            interval=3,
            error_message="OPA did not receive policies within timeout"
        )

        assert success, "OPA does not have any policies loaded"
