"""
End-to-end tests for client registration via Statistics API.

Validates that the OPAL client successfully registers with the server
and appears in the statistics endpoint.
"""

import pytest

from tests.e2e.utils.http_client import http_get_with_retries


def test_statistics_api_is_enabled(opal_server_url):
    """Test that Statistics API is enabled and accessible."""
    url = f"{opal_server_url}/statistics"
    response = http_get_with_retries(url, max_attempts=10)
    
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Statistics API may not be enabled."
    )


def test_client_appears_in_statistics(opal_server_url):
    """Test that OPAL client is registered in server statistics."""
    url = f"{opal_server_url}/statistics"
    response = http_get_with_retries(url, max_attempts=15, timeout=15)
    
    assert response.status_code == 200, "Statistics endpoint should return 200"
    
    data = response.json()
    
    # Verify statistics structure
    assert "clients" in data, "Statistics should contain 'clients' field"
    assert isinstance(data["clients"], dict), "Clients should be a dictionary"
    
    # Check that at least one client is registered
    client_count = len(data["clients"])
    assert client_count > 0, (
        f"Expected at least one client registered, found {client_count}. "
        f"Client may not have connected yet."
    )


def test_client_has_registered_topics(opal_server_url):
    """Test that registered client has subscribed to topics."""
    url = f"{opal_server_url}/statistics"
    response = http_get_with_retries(url, max_attempts=15, timeout=15)
    
    assert response.status_code == 200, "Statistics endpoint should return 200"
    
    data = response.json()
    clients = data.get("clients", {})
    
    # Find a client and verify it has topics
    assert len(clients) > 0, "At least one client should be registered"
    
    # Each client can have multiple channels, check at least one has topics
    client_has_topics = False
    for client_id, channels in clients.items():
        if not isinstance(channels, list):
            continue
        for channel in channels:
            if isinstance(channel, dict) and "topics" in channel:
                topics = channel.get("topics", [])
                if len(topics) > 0:
                    client_has_topics = True
                    break
        if client_has_topics:
            break
    
    assert client_has_topics, (
        "At least one registered client should have subscribed to topics. "
        "Client may not have completed initial subscription."
    )


def test_statistics_brief_endpoint_works(opal_server_url):
    """Test that the brief statistics endpoint returns client count."""
    url = f"{opal_server_url}/stats"
    response = http_get_with_retries(url, max_attempts=10)
    
    assert response.status_code == 200, "Stats endpoint should return 200"
    
    data = response.json()
    
    # Verify brief stats structure
    assert "client_count" in data, "Brief stats should contain 'client_count'"
    assert "server_count" in data, "Brief stats should contain 'server_count'"
    
    # Verify client count is at least 1
    client_count = data.get("client_count", 0)
    assert client_count >= 1, (
        f"Expected at least 1 client, found {client_count}"
    )
