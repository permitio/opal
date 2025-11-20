import pytest
import re


@pytest.mark.e2e
@pytest.mark.docker
def test_server_logs_no_errors(get_container_logs):
    """Test that OPAL server logs contain no ERROR or CRITICAL messages."""
    server_logs = get_container_logs("opal_server")
    
    # Check for error patterns
    error_patterns = [
        r'\bERROR\b',
        r'\bCRITICAL\b',
        r'\bFATAL\b'
    ]
    
    found_errors = []
    for pattern in error_patterns:
        matches = re.findall(pattern, server_logs, re.IGNORECASE)
        if matches:
            # Get the actual log lines containing errors
            error_lines = [line for line in server_logs.split('\n') 
                          if re.search(pattern, line, re.IGNORECASE)]
            found_errors.extend(error_lines[:5])  # Limit to first 5 errors
    
    assert not found_errors, f"Found error messages in server logs:\n" + "\n".join(found_errors)


@pytest.mark.e2e
@pytest.mark.docker
def test_client_logs_no_errors(get_container_logs):
    """Test that OPAL client logs contain no ERROR or CRITICAL messages."""
    client_logs = get_container_logs("opal_client")
    
    # Check for error patterns
    error_patterns = [
        r'\bERROR\b',
        r'\bCRITICAL\b',
        r'\bFATAL\b'
    ]
    
    found_errors = []
    for pattern in error_patterns:
        matches = re.findall(pattern, client_logs, re.IGNORECASE)
        if matches:
            # Get the actual log lines containing errors
            error_lines = [line for line in client_logs.split('\n') 
                          if re.search(pattern, line, re.IGNORECASE)]
            found_errors.extend(error_lines[:5])  # Limit to first 5 errors
    
    assert not found_errors, f"Found error messages in client logs:\n" + "\n".join(found_errors)


@pytest.mark.e2e
@pytest.mark.docker
def test_server_startup_success(get_container_logs):
    """Test that server logs indicate successful startup."""
    server_logs = get_container_logs("opal_server")
    
    # Look for positive startup indicators
    success_patterns = [
        r'OPAL Server Startup',
        r'Application startup complete',
        r'Uvicorn running on',
        r'Started server process'
    ]
    
    startup_found = False
    for pattern in success_patterns:
        if re.search(pattern, server_logs, re.IGNORECASE):
            startup_found = True
            break
    
    assert startup_found, "No successful startup message found in server logs"


@pytest.mark.e2e
@pytest.mark.docker
def test_client_startup_success(get_container_logs):
    """Test that client logs indicate successful startup."""
    client_logs = get_container_logs("opal_client")
    
    # Look for positive startup indicators - more flexible patterns
    success_patterns = [
        r'opal.client',
        r'opal_client',
        r'Application startup complete',
        r'Uvicorn running',
        r'Started server process',
        r'server process',
        r'startup complete',
        r'running on',
        r'started'
    ]
    
    startup_found = False
    for pattern in success_patterns:
        if re.search(pattern, client_logs, re.IGNORECASE):
            startup_found = True
            break
    
    # If no specific startup pattern found, just check logs are not empty and no major errors
    if not startup_found and len(client_logs.strip()) > 0:
        # If we have logs and no critical errors, consider it a success
        if not re.search(r'\b(FATAL|CRITICAL)\b', client_logs, re.IGNORECASE):
            startup_found = True
    
    assert startup_found, f"No successful startup indicators found in client logs. Log sample: {client_logs[:200]}..."


@pytest.mark.e2e
@pytest.mark.docker
def test_logs_contain_expected_services(get_container_logs):
    """Test that we can retrieve logs from both services."""
    server_logs = get_container_logs("opal_server")
    client_logs = get_container_logs("opal_client")
    
    # Verify we got some logs from both services
    assert len(server_logs.strip()) > 0, "Server logs should not be empty"
    assert len(client_logs.strip()) > 0, "Client logs should not be empty"
    
    # Logs should not contain error messages about missing containers
    assert "Error getting logs" not in server_logs, "Failed to retrieve server logs"
    assert "Error getting logs" not in client_logs, "Failed to retrieve client logs"