"""
Log parsing utilities for E2E tests.

Provides functions to retrieve and analyze Docker container logs.
"""

from typing import Optional

from tests.e2e.utils.docker_compose import get_compose_file_path, get_compose_services, run_compose_command


def get_container_logs(service_name: str) -> str:
    """
    Get logs from a specific Docker Compose service.
    
    Example:
        logs = get_container_logs("opal_server")
        print(logs)
    
    Args:
        service_name: Name of the service (e.g., "opal_server", "opal_client")
    
    Returns:
        Log output as a string
    """
    result = run_compose_command(["logs", "--no-color", service_name], check=False)
    return result.stdout


def get_all_container_logs() -> dict[str, str]:
    """
    Get logs from all Docker Compose services.
    
    Uses get_compose_services() as the source of truth to ensure all services
    are included, even if they have no log output yet.
    
    Example:
        all_logs = get_all_container_logs()
        print(all_logs["opal_server"])
    
    Returns:
        Dictionary mapping service names to their log output (empty string if no logs)
    """
    # Get list of all services from Docker Compose (source of truth)
    services = get_compose_services()
    
    # Initialize dictionary with all services (ensures all services are present)
    logs_by_service: dict[str, list[str]] = {service: [] for service in services}
    
    # Get logs from Docker Compose
    result = run_compose_command(["logs", "--no-color"], check=False)
    
    # Parse logs by service
    # Docker Compose logs format: "service_name | log line"
    current_service: Optional[str] = None
    
    for line in result.stdout.split("\n"):
        if not line.strip():
            continue
        
        # Check if line has service prefix (format: "service_name | log content")
        if "|" in line:
            parts = line.split("|", 1)
            service_name = parts[0].strip()
            log_content = parts[1].strip()
            
            # Only process services that are in our known services list
            if service_name in logs_by_service:
                logs_by_service[service_name].append(log_content)
                current_service = service_name
            else:
                # Unknown service in logs (shouldn't happen, but handle gracefully)
                current_service = None
        elif current_service and current_service in logs_by_service:
            # Continuation of previous log line (multi-line log entry)
            logs_by_service[current_service].append(line.strip())
    
    # Convert lists to strings (empty string if no logs)
    return {service: "\n".join(lines) for service, lines in logs_by_service.items()}


def is_benign_startup_error(line: str) -> bool:
    """
    Check if an ERROR log line represents a benign transient startup error.
    
    Filters out known transient errors that occur during normal startup:
    - Connection retries (connection refused, connection errors)
    - Temporary connection failures that resolve
    - Startup warnings that don't indicate fatal issues
    - Datadog tracing errors (expected when Datadog agent is not running)
    
    Args:
        line: Log line to check
    
    Returns:
        True if the error is benign/transient, False if it's a real error
    """
    line_lower = line.lower()
    
    # Known benign startup error patterns
    benign_patterns = [
        "connection refused",
        "connection error",
        "connection failed",
        "trying to connect",
        "retry",
        "retrying",
        "waiting for",
        "timeout",
        "temporary failure",
        "name resolution",
        "dns",
        # Datadog tracing errors: expected when Datadog agent is not running
        # These are non-fatal and do not indicate OPAL startup/runtime failures
        "ddtrace.internal.writer",
        "failed to send traces",
    ]
    
    # If line contains any benign pattern, it's likely a transient startup error
    for pattern in benign_patterns:
        if pattern in line_lower:
            return True
    
    return False


def check_logs_for_errors(
    service_name: Optional[str] = None,
    error_keywords: Optional[list[str]] = None,
    ignore_benign_startup_errors: bool = True,
) -> list[str]:
    """
    Check container logs for ERROR or CRITICAL messages.
    
    Filters out transient startup errors by default, focusing on fatal or
    persistent errors that indicate real problems.
    
    Example:
        errors = check_logs_for_errors("opal_server")
        if errors:
            print("Found errors:", errors)
    
    Args:
        service_name: Specific service to check (None checks all services)
        error_keywords: Keywords to search for (default: ["ERROR", "CRITICAL"])
        ignore_benign_startup_errors: If True, filter out known transient startup errors
    
    Returns:
        List of error messages found (empty list if no errors)
    """
    if error_keywords is None:
        error_keywords = ["ERROR", "CRITICAL"]
    
    errors = []
    
    # Get logs from one service or all services
    if service_name:
        logs = get_container_logs(service_name)
        log_sources = {service_name: logs}
    else:
        log_sources = get_all_container_logs()
    
    # Search each log line for error keywords
    for service, log_content in log_sources.items():
        for line in log_content.split("\n"):
            if not line.strip():
                continue
            
            # Check for error keywords (case-insensitive)
            line_lower = line.lower()
            has_error_keyword = False
            for keyword in error_keywords:
                if keyword.lower() in line_lower:
                    has_error_keyword = True
                    break
            
            if has_error_keyword:
                # CRITICAL errors are always considered real errors
                if "critical" in line_lower or "fatal" in line_lower:
                    errors.append(f"[{service}] {line.strip()}")
                # For ERROR logs, filter out benign startup errors if enabled
                elif not ignore_benign_startup_errors or not is_benign_startup_error(line):
                    errors.append(f"[{service}] {line.strip()}")
    
    return errors
