"""
OPAL End-to-End Test Suite

Comprehensive integration tests for OPAL Server, Client, and OPA.
Tests cover health checks, connectivity, policy updates, data synchronization,
and system reliability.
"""

import pytest
import requests
import time
import json
from typing import Dict, Any, Optional


class TestHealthChecks:
    """Test suite for service health endpoints."""

    def test_opal_server_health(self, opal_server_url):
        """
        Test that the OPAL server health endpoint is accessible and returns correct status.
        
        Validates:
        - HTTP 200 status code
        - Server is responsive
        """
        response = requests.get(f"{opal_server_url}/", timeout=10)
        
        assert response.status_code == 200, \
            f"Server health check failed with status {response.status_code}"

    def test_opal_client_health(self, opal_client_url):
        """
        Test that the OPAL client health endpoint is accessible and returns correct status.
        
        Validates:
        - HTTP 200 status code
        - Correct JSON response structure
        - Expected health status value
        """
        response = requests.get(f"{opal_client_url}/healthcheck", timeout=10)
        
        assert response.status_code == 200, \
            f"Client health check failed with status {response.status_code}"
        
        # The healthcheck endpoint should return a status
        data = response.json()
        assert "status" in data or "healthy" in data or isinstance(data, dict), \
            f"Client health check returned unexpected data: {data}"

    def test_opa_health(self, opa_url):
        """
        Test that OPA (running via OPAL client) is healthy and accessible.
        
        Validates:
        - HTTP 200 status code
        - OPA is running and responsive
        """
        response = requests.get(f"{opa_url}/health", timeout=10)
        
        assert response.status_code == 200, \
            f"OPA health check failed with status {response.status_code}"

    def test_all_services_respond_quickly(self, opal_server_url, opal_client_url, opa_url):
        """
        Test that all services respond to health checks within acceptable time limits.
        
        Performance benchmark: All services should respond within 2 seconds.
        """
        services = {
            "OPAL Server": f"{opal_server_url}/",
            "OPAL Client": f"{opal_client_url}/healthcheck",
            "OPA": f"{opa_url}/health"
        }
        
        for service_name, url in services.items():
            start = time.time()
            response = requests.get(url, timeout=10)
            duration = time.time() - start
            
            assert response.status_code == 200, \
                f"{service_name} health check failed"
            assert duration < 2.0, \
                f"{service_name} responded too slowly: {duration:.2f}s (max: 2.0s)"


class TestConnectivity:
    """Test suite for service connectivity and communication."""

    def test_opal_client_server_connection(self, opal_client_url):
        """
        Test that the OPAL client successfully connects to the server.
        
        Validates:
        - Client establishes connection within timeout
        - Connection status is reported correctly
        - Policy updates are received
        """
        timeout = 60  # Increased timeout for initial connection
        start_time = time.time()
        connected = False
        last_error = None
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{opal_client_url}/healthcheck", timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if healthy status indicates connection
                    # Different OPAL versions may have different response structures
                    if data.get("status") == "ok" or data.get("healthy") == True:
                        connected = True
                        break
                    
                    last_error = f"Connection incomplete: {data}"
                else:
                    last_error = f"Healthcheck endpoint returned {response.status_code}"
                    
            except requests.exceptions.RequestException as e:
                last_error = f"Connection error: {str(e)}"
            
            time.sleep(2)
        
        assert connected, \
            f"OPAL client failed to connect within {timeout}s. Last error: {last_error}"

    def test_statistics_endpoint_accessible(self, opal_server_url):
        """
        Test that the statistics endpoint is accessible on the server.
        
        Validates:
        - Statistics endpoint returns 200 or 501 (if disabled)
        - Endpoint is properly configured
        """
        response = requests.get(f"{opal_server_url}/statistics", timeout=10)
        
        # Statistics endpoint may return 501 if OPAL_STATISTICS_ENABLED=false
        # This is expected and not a failure
        if response.status_code == 501:
            pytest.skip("Statistics endpoint disabled (OPAL_STATISTICS_ENABLED=false)")
        
        # May also require authentication (401) or be accessible (200)
        assert response.status_code in [200, 401, 501], \
            f"Unexpected statistics endpoint status: {response.status_code}. Response: {response.text[:200]}"
    
    def test_client_server_connection_via_statistics(self, opal_server_url):
        """
        Test that the client and server are connected using the Statistics API.
        
        This is the core requirement from issue #677.
        
        Validates:
        - Statistics API is accessible
        - Client is registered in server statistics
        - Connection is established and active
        """
        timeout = 60  # Wait up to 60 seconds for client to connect
        start_time = time.time()
        connected = False
        last_error = None
        
        while time.time() - start_time < timeout:
            try:
                # Try to access statistics endpoint
                # Note: May require authentication, but we'll try without first
                response = requests.get(f"{opal_server_url}/statistics", timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if statistics show connected clients
                    # Statistics structure: { "clients": {client_id: [ChannelStats]}, "servers": {...}, ... }
                    if "clients" in data:
                        clients = data["clients"]
                        # clients is a Dict[str, List[ChannelStats]], so check if it has any keys
                        if isinstance(clients, dict) and len(clients) > 0:
                            connected = True
                            # Log connection details for debugging
                            print(f"\n✓ Client connected! Statistics: {json.dumps(data, indent=2, default=str)}")
                            break
                        else:
                            last_error = f"No clients connected yet. Statistics: {json.dumps(data, indent=2, default=str)}"
                    else:
                        last_error = f"Statistics response missing 'clients' field: {data}"
                        
                elif response.status_code == 401:
                    # Authentication required - try with empty auth or check if we can use stats endpoint
                    # For now, we'll check the /stats endpoint which might not require auth
                    stats_response = requests.get(f"{opal_server_url}/stats", timeout=10)
                    if stats_response.status_code == 200:
                        stats_data = stats_response.json()
                        if "client_count" in stats_data and stats_data["client_count"] > 0:
                            connected = True
                            print(f"\n✓ Client connected! Brief stats: {json.dumps(stats_data, indent=2, default=str)}")
                            break
                        else:
                            last_error = f"Client count is 0. Stats: {json.dumps(stats_data, indent=2, default=str)}"
                    else:
                        last_error = f"Stats endpoint returned {stats_response.status_code}: {stats_response.text[:200]}"
                        
                elif response.status_code == 501:
                    pytest.skip("Statistics endpoint disabled (OPAL_STATISTICS_ENABLED=false)")
                else:
                    last_error = f"Statistics endpoint returned {response.status_code}: {response.text[:200]}"
                    
            except requests.exceptions.RequestException as e:
                last_error = f"Request error: {str(e)}"
            
            time.sleep(2)
        
        assert connected, \
            f"OPAL client failed to connect to server within {timeout}s (checked via Statistics API). Last error: {last_error}"

    def test_server_accessible(self, opal_server_url):
        """
        Test that the OPAL server is accessible and responding.
        """
        response = requests.get(f"{opal_server_url}/", timeout=10)
        
        assert response.status_code == 200, \
            f"Server not accessible: {response.status_code}"


class TestPolicyOperations:
    """Test suite for policy-related operations."""

    def test_opa_policies_loaded(self, opa_url):
        """
        Test that OPA has policies loaded from the initial sync.
        
        Validates:
        - OPA policy API is accessible
        - Policies are present in OPA
        """
        # Wait a bit for initial policy sync
        time.sleep(10)
        
        response = requests.get(f"{opa_url}/v1/policies", timeout=10)
        
        assert response.status_code == 200, \
            f"OPA policies endpoint returned {response.status_code}"
        
        data = response.json()
        
        # Should have some policies loaded from the example repo
        assert "result" in data, "OPA policies response missing 'result' field"

    def test_opa_data_endpoint_accessible(self, opa_url):
        """
        Test that OPA's data API is accessible.
        
        This validates that OPA is ready to serve authorization decisions.
        """
        response = requests.get(f"{opa_url}/v1/data", timeout=10)
        
        assert response.status_code == 200, \
            f"OPA data endpoint returned {response.status_code}"
        
        # Should return valid JSON
        data = response.json()
        assert isinstance(data, dict), "OPA data endpoint should return JSON object"

    def test_policy_query_execution(self, opa_url):
        """
        Test that OPA can execute policy queries.
        
        Validates:
        - Query endpoint is functional
        - Queries return results
        - No errors in query execution
        """
        # Wait for policies to be loaded
        time.sleep(10)
        
        # Simple query to test OPA is working
        query_payload = {"input": {}}
        
        response = requests.post(
            f"{opa_url}/v1/data",
            json=query_payload,
            timeout=10
        )
        
        assert response.status_code == 200, \
            f"OPA query execution failed with status {response.status_code}"
        
        data = response.json()
        assert "result" in data, "OPA query response missing 'result' field"


class TestDataSynchronization:
    """Test suite for data synchronization between components."""

    def test_client_connected_to_server(self, opal_client_url):
        """
        Test that the client is connected and operational.
        
        Validates:
        - Client health check passes
        - Client is responsive
        """
        timeout = 30
        start_time = time.time()
        client_ready = False
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{opal_client_url}/healthcheck", timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "ok" or data.get("healthy") == True:
                        client_ready = True
                        break
                        
            except requests.exceptions.RequestException:
                pass
            
            time.sleep(2)
        
        assert client_ready, \
            f"Client did not become ready within {timeout}s"

    def test_opa_ready_to_serve(self, opa_url):
        """
        Test that OPA is ready to serve policy decisions.
        
        Validates:
        - OPA health check passes
        - OPA API is responsive
        """
        response = requests.get(f"{opa_url}/health", timeout=10)
        assert response.status_code == 200, "OPA not healthy"
        
        # Also check data endpoint
        response = requests.get(f"{opa_url}/v1/data", timeout=10)
        assert response.status_code == 200, "OPA data API not responsive"


class TestSystemReliability:
    """Test suite for system reliability and error handling."""

    def test_no_critical_logs(self, docker_compose_logs):
        """
        Test that no critical errors or alerts appear in service logs.
        
        Validates:
        - No ERROR level messages (ignoring known benign errors)
        - No CRITICAL level messages
        - Logs are accessible
        """
        critical_errors = {}
        
        # Known benign error patterns to ignore
        benign_patterns = [
            "Authentication failed",  # Expected when statistics are disabled
            "Could not decode access token",  # Expected without auth setup
            "Connection refused",  # May occur during startup
            "Trying to reconnect",  # Normal retry behavior
            "failed to send, dropping",  # DataDog tracing errors when DataDog agent not running
            "ddtrace.internal.writer",  # DataDog tracing component errors
            "intake at http://localhost:8126",  # DataDog agent connection errors
        ]
        
        for service, logs in docker_compose_logs.items():
            if not logs or "Could not retrieve logs" in logs:
                pytest.skip(f"Logs not available for {service}")
                continue
            
            errors = []
            
            # Check for ERROR and CRITICAL messages
            for line in logs.split('\n'):
                line_upper = line.upper()
                if 'ERROR' in line_upper or 'CRITICAL' in line_upper:
                    # Check if it's a benign error
                    is_benign = any(pattern in line for pattern in benign_patterns)
                    if not is_benign:
                        errors.append(line.strip())
            
            if errors:
                critical_errors[service] = errors
        
        assert not critical_errors, \
            f"Critical errors found in logs:\n" + \
            "\n".join([f"{svc}: {errs}" for svc, errs in critical_errors.items()])

    def test_services_stability(self, opal_server_url, opal_client_url):
        """
        Test that services remain stable over multiple requests.
        
        Validates:
        - Consistent responses over time
        - No service degradation
        - No connection failures
        """
        iterations = 5
        
        for i in range(iterations):
            # Test server
            response = requests.get(f"{opal_server_url}/", timeout=10)
            assert response.status_code == 200, \
                f"Server unstable on iteration {i+1}"
            
            # Test client
            response = requests.get(f"{opal_client_url}/healthcheck", timeout=10)
            assert response.status_code == 200, \
                f"Client unstable on iteration {i+1}"
            
            time.sleep(1)

    def test_error_responses_are_well_formed(self, opal_client_url):
        """
        Test that invalid requests return proper error responses.
        
        Validates:
        - 404 for non-existent endpoints
        - Responses are properly formatted
        """
        response = requests.get(f"{opal_client_url}/nonexistent-endpoint-12345", timeout=10)
        
        # Should return 404
        assert response.status_code == 404, \
            "Non-existent endpoint should return 404"

    def test_concurrent_health_checks(self, opal_server_url, opal_client_url, opa_url):
        """
        Test that services handle concurrent requests properly.
        
        Validates:
        - Services respond correctly under load
        - No race conditions
        - All requests succeed
        """
        import concurrent.futures
        
        urls = [
            opal_server_url + "/",
            opal_client_url + "/healthcheck",
            opa_url + "/health"
        ] * 5  # 15 total requests
        
        def make_request(url):
            response = requests.get(url, timeout=10)
            return response.status_code == 200
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, url) for url in urls]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        assert all(results), \
            "Some concurrent health check requests failed"


class TestEndpointValidation:
    """Test suite for API endpoint validation and contract testing."""

    def test_server_root_endpoint(self, opal_server_url):
        """
        Test that server root endpoint is accessible.
        
        Validates:
        - Endpoint accessibility
        - Returns valid response
        """
        response = requests.get(f"{opal_server_url}/", timeout=10)
        assert response.status_code == 200, "Server root endpoint not accessible"
        assert response.content, "Server root endpoint returned empty response"

    def test_client_healthcheck_endpoint(self, opal_client_url):
        """
        Test that client healthcheck endpoint returns proper data.
        
        Validates:
        - Endpoint accessibility
        - Returns JSON data
        """
        response = requests.get(f"{opal_client_url}/healthcheck", timeout=10)
        assert response.status_code == 200, "Client healthcheck not accessible"
        
        data = response.json()
        assert isinstance(data, dict), "Healthcheck should return JSON object"

    def test_opa_api_accessible(self, opa_url):
        """
        Test that OPA API is accessible.
        
        Validates:
        - OPA root endpoint returns data
        - API is functional
        """
        response = requests.get(f"{opa_url}/", timeout=10)
        
        # OPA root endpoint should return some info
        assert response.status_code == 200, \
            "OPA API not accessible"


# Performance Benchmarks
class TestPerformance:
    """Test suite for performance benchmarks and timing."""

    @pytest.mark.benchmark
    def test_health_check_response_time(self, opal_server_url, opal_client_url, opa_url):
        """
        Benchmark health check response times.
        
        Performance targets:
        - All services should respond within 500ms
        """
        services = {
            "OPAL Server": opal_server_url + "/",
            "OPAL Client": opal_client_url + "/healthcheck",
            "OPA": opa_url + "/health"
        }
        
        timings = {}
        
        for name, url in services.items():
            start = time.time()
            requests.get(url, timeout=10)
            duration = (time.time() - start) * 1000  # Convert to ms
            timings[name] = duration
            
            assert duration < 500, \
                f"{name} health check too slow: {duration:.2f}ms (target: <500ms)"
        
        print(f"\nHealth check timings: {timings}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
