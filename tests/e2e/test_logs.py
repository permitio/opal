import pytest


@pytest.mark.e2e
class TestLogs:
    """Tests for log validation - ensuring no errors or critical issues."""

    def test_server_no_error_logs(self, server_logs):
        """Verify server logs contain no ERROR level messages."""
        error_lines = server_logs.filter_by_level("ERROR")

        # Filter out known non-error logs (like ddtrace connection attempts)
        real_errors = [
            line for line in error_lines
            if "ddtrace" not in line.lower()
        ]

        assert len(real_errors) == 0, \
            f"Found {len(real_errors)} ERROR log entries in server logs:\n" + \
            "\n".join(real_errors[:10])

    def test_server_no_critical_logs(self, server_logs):
        """Verify server logs contain no CRITICAL level messages."""
        critical_lines = server_logs.filter_by_level("CRITICAL")

        assert len(critical_lines) == 0, \
            f"Found {len(critical_lines)} CRITICAL log entries in server logs:\n" + \
            "\n".join(critical_lines[:10])

    def test_client_no_error_logs(self, client_logs):
        """Verify client logs contain no ERROR level messages."""
        error_lines = client_logs.filter_by_level("ERROR")

        assert len(error_lines) == 0, \
            f"Found {len(error_lines)} ERROR log entries in client logs:\n" + \
            "\n".join(error_lines[:10])

    def test_client_no_critical_logs(self, client_logs):
        """Verify client logs contain no CRITICAL level messages."""
        critical_lines = client_logs.filter_by_level("CRITICAL")

        assert len(critical_lines) == 0, \
            f"Found {len(critical_lines)} CRITICAL log entries in client logs:\n" + \
            "\n".join(critical_lines[:10])

    def test_server_has_startup_logs(self, server_logs):
        """Verify server has expected startup messages."""
        logs_text = server_logs.get_all().lower()

        startup_indicators = [
            "uvicorn",
            "started",
            "application startup"
        ]

        found = [indicator for indicator in startup_indicators if indicator in logs_text]

        assert len(found) > 0, \
            f"No startup indicators found in server logs. Expected one of: {startup_indicators}"

    def test_client_has_startup_logs(self, client_logs):
        """Verify client has expected startup messages."""
        logs_text = client_logs.get_all().lower()

        startup_indicators = [
            "opal",
            "started",
            "client"
        ]

        found = [indicator for indicator in startup_indicators if indicator in logs_text]

        assert len(found) > 0, \
            f"No startup indicators found in client logs. Expected one of: {startup_indicators}"

    def test_no_exception_tracebacks_in_server(self, server_logs):
        """Verify server logs contain no exception tracebacks."""
        logs = server_logs.get_all()

        traceback_indicators = [
            "Traceback (most recent call last)",
            "File \"",
        ]

        traceback_lines = []
        for indicator in traceback_indicators:
            traceback_lines.extend(server_logs.search(indicator, case_sensitive=True))

        assert len(traceback_lines) == 0, \
            f"Found {len(traceback_lines)} traceback entries in server logs"

    def test_no_exception_tracebacks_in_client(self, client_logs):
        """Verify client logs contain no exception tracebacks."""
        logs = client_logs.get_all()

        traceback_indicators = [
            "Traceback (most recent call last)",
            "File \"",
        ]

        traceback_lines = []
        for indicator in traceback_indicators:
            traceback_lines.extend(client_logs.search(indicator, case_sensitive=True))

        assert len(traceback_lines) == 0, \
            f"Found {len(traceback_lines)} traceback entries in client logs"

    def test_server_logs_accessible(self, server_logs):
        """Verify we can access server logs."""
        logs = server_logs.get_all()
        assert logs is not None, "Server logs should not be None"
        assert len(logs) > 0, "Server logs should not be empty"

    def test_client_logs_accessible(self, client_logs):
        """Verify we can access client logs."""
        logs = client_logs.get_all()
        assert logs is not None, "Client logs should not be None"
        assert len(logs) > 0, "Client logs should not be empty"
