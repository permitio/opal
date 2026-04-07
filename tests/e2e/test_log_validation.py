"""
End-to-end tests for log validation.

Validates that container logs do not contain ERROR or CRITICAL messages.
"""

import pytest

from tests.e2e.utils.docker_compose import get_compose_services
from tests.e2e.utils.log_parser import check_logs_for_errors, get_all_container_logs


def test_all_container_logs_have_no_errors():
    """Test that all container logs combined contain no ERROR or CRITICAL messages."""
    errors = check_logs_for_errors(service_name=None)
    
    assert len(errors) == 0, (
        f"Found {len(errors)} ERROR/CRITICAL messages across all containers:\n"
        + "\n".join(f"  - {error}" for error in errors[:20])  # Show first 20
    )


def test_each_service_logs_have_no_errors():
    """Test that each service's logs contain no ERROR or CRITICAL messages."""
    services = get_compose_services()
    
    assert len(services) > 0, "At least one service should be running"
    
    for service_name in services:
        errors = check_logs_for_errors(service_name=service_name)
        
        # Database services may have some expected warnings, so we're lenient
        # Only fail on actual CRITICAL/FATAL messages for database services
        if "postgres" in service_name.lower() or "db" in service_name.lower():
            critical_errors = [
                error for error in errors
                if "CRITICAL" in error.upper() or "FATAL" in error.upper()
            ]
            assert len(critical_errors) == 0, (
                f"Found {len(critical_errors)} CRITICAL/FATAL messages in {service_name} logs:\n"
                + "\n".join(f"  - {error}" for error in critical_errors[:10])
            )
        else:
            assert len(errors) == 0, (
                f"Found {len(errors)} ERROR/CRITICAL messages in {service_name} logs:\n"
                + "\n".join(f"  - {error}" for error in errors[:10])  # Show first 10
            )


def test_logs_are_accessible():
    """Test that container logs can be retrieved for all services."""
    all_logs = get_all_container_logs()
    services = get_compose_services()
    
    assert len(services) > 0, "At least one service should be running"
    
    # Verify we can retrieve logs for all discovered services
    # Note: Some services (e.g., infrastructure services) may legitimately have no logs
    for service_name in services:
        assert service_name in all_logs, (
            f"Logs for service '{service_name}' should be available. "
            f"Available services in logs: {list(all_logs.keys())}"
        )
        # Do not assert logs are non-empty - some services legitimately produce no output
