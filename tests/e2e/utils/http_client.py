"""
HTTP client with retries for E2E tests.

Provides a simple HTTP GET function that automatically retries on failures
with exponential backoff.
"""

import time
from typing import Any

import requests


def http_get_with_retries(
    url: str,
    max_attempts: int = 5,
    timeout: int = 10,
    **kwargs: Any,
) -> requests.Response:
    """
    Make an HTTP GET request with automatic retries.
    
    Retries on connection errors, timeouts, and server errors (5xx).
    Uses exponential backoff: waits 0.5s, 1s, 2s, 4s, 8s between attempts.
    
    Example:
        response = http_get_with_retries("http://localhost:17002/healthcheck")
        assert response.status_code == 200
    
    Args:
        url: The URL to request
        max_attempts: Maximum number of retry attempts (default: 5)
        timeout: Request timeout in seconds (default: 10)
        **kwargs: Additional arguments passed to requests.get()
    
    Returns:
        Response object from requests library
    
    Raises:
        requests.RequestException: If all retry attempts fail
    """
    last_error = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, timeout=timeout, **kwargs)
            
            # Success if status code is not a server error
            if response.status_code < 500:
                return response
            
            # For 5xx errors, raise to trigger retry
            response.raise_for_status()
            
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            last_error = e
            
            # Don't wait after the last attempt
            if attempt < max_attempts:
                # Exponential backoff: 0.5s, 1s, 2s, 4s, 8s
                wait_seconds = (2 ** (attempt - 1)) * 0.5
                time.sleep(wait_seconds)
    
    # All attempts failed - raise with helpful error message
    error_msg = (
        f"Failed to GET {url} after {max_attempts} attempts.\n"
        f"Last error: {type(last_error).__name__}: {last_error}"
    )
    raise requests.RequestException(error_msg) from last_error
