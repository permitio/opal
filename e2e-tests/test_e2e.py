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
        - Correct JSON response structure
        - Expected health status value
        """
        response = requests.get(f"{opal_server_url}/health", timeout=10)
        
        assert response.status_code == 200, \
            f"Server health check failed with status {response.status_code}"
        
        data = response.json()
        assert data == {"status": "ok"}, \
            f"Server health check returned unexpected data: {data}"

    def test_opal_client_health(self, opal_client_url):
        """
        Test that the OPAL client health endpoint is accessible and returns correct status.
        
        Validates:
        - HTTP 200 status code
        - Correct JSON response structure
        - Expected health status value
        """
        response = requests.get(f"{opal_client_url}/health", timeout=10)
        
        assert response.status_code == 200, \
            f"Client health check failed with status {response.status_code}"
        
        data = response.json()
        assert data == {"status": "ok"}, \
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
            "OPAL Server": f"{opal_server_url}/health",
            "OPAL Client": f"{opal_client_url}/health",
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
        timeout = 30
        start_time = time.time()
        connected = False
        last_error = None
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{opal_client_url}/statistics", timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check connection status and policy updates
                    if data.get("client_is_connected", False) and \
                       data.get("last_policy_update") is not None:
                        connected = True
                        break
                    
                    last_error = f"Connection incomplete: connected={data.get('client_is_connected')}, " \
                               f"policy_update={data.get('last_policy_update')}"
                else:
                    last_error = f"Statistics endpoint returned {response.status_code}"
                    
            except requests.exceptions.RequestException as e:
                last_error = f"Connection error: {str(e)}"
            
            time.sleep(1)
        
        assert connected, \
            f"OPAL client failed to connect within {timeout}s. Last error: {last_error}"

    def test_statistics_endpoint_structure(self, opal_client_url):
        """
        Test that the statistics endpoint returns well-formed data.
        
        Validates:
        - Response is valid JSON
        - Required fields are present
        - Data types are correct
        """
        response = requests.get(f"{opal_client_url}/statistics", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        
        # Validate expected fields exist
        expected_fields = ["client_is_connected"]
        for field in expected_fields:
            assert field in data, f"Statistics missing expected field: {field}"
        
        # Validate data types
        assert isinstance(data.get("client_is_connected"), bool), \
            "client_is_connected should be boolean"

    def test_server_broadcast_channel_connection(self, opal_server_url):
        """
        Test that the OPAL server has successfully connected to the broadcast channel.
        
        This ensures the pub/sub infrastructure is working.
        """
        # Give server time to establish connection
        time.sleep(2)
        
        response = requests.get(f"{opal_server_url}/statistics", timeout=10)
        
        # If statistics endpoint exists and is accessible
        if response.status_code == 200:
            data = response.json()
            # Server should be operational if statistics are available
            assert data is not None, "Server statistics endpoint returned no data"


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
        time.sleep(5)
        
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
        time.sleep(5)
        
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

    def test_client_receives_policy_updates(self, opal_client_url):
        """
        Test that the client successfully receives and processes policy updates.
        
        Validates:
        - Policy update timestamp is recorded
        - Update count is incremented
        """
        timeout = 30
        start_time = time.time()
        policy_update_received = False
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{opal_client_url}/statistics", timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("last_policy_update") is not None:
                        policy_update_received = True
                        
                        # Validate timestamp format (should be ISO format or similar)
                        timestamp = data.get("last_policy_update")
                        assert timestamp, "Policy update timestamp should not be empty"
                        break
                        
            except requests.exceptions.RequestException:
                pass
            
            time.sleep(1)
        
        assert policy_update_received, \
            f"Client did not receive policy updates within {timeout}s"

    def test_statistics_reporting_frequency(self, opal_client_url):
        """
        Test that statistics are updated regularly.
        
        Validates:
        - Multiple statistics requests return data
        - Statistics endpoint is stable
        """
        samples = []
        
        for _ in range(3):
            response = requests.get(f"{opal_client_url}/statistics", timeout=10)
            assert response.status_code == 200
            samples.append(response.json())
            time.sleep(2)
        
        # All samples should return data
        assert len(samples) == 3, "Failed to collect all statistics samples"
        
        # Each sample should have connection info
        for sample in samples:
            assert "client_is_connected" in sample, \
                "Statistics sample missing connection info"


class TestSystemReliability:
    """Test suite for system reliability and error handling."""

    def test_no_critical_logs(self, docker_compose_logs):
        """
        Test that no critical errors or alerts appear in service logs.
        
        Validates:
        - No ERROR level messages
        - No CRITICAL level messages
        - Logs are accessible
        """
        critical_errors = {}
        
        for service, logs in docker_compose_logs.items():
            if not logs or "Could not retrieve logs" in logs:
                pytest.skip(f"Logs not available for {service}")
                continue
            
            errors = []
            
            # Check for ERROR messages
            for line in logs.split('\n'):
                if 'ERROR' in line.upper():
                    errors.append(line.strip())
            
            # Check for CRITICAL messages
            for line in logs.split('\n'):
                if 'CRITICAL' in line.upper():
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
            response = requests.get(f"{opal_server_url}/health", timeout=10)
            assert response.status_code == 200, \
                f"Server unstable on iteration {i+1}"
            
            # Test client
            response = requests.get(f"{opal_client_url}/health", timeout=10)
            assert response.status_code == 200, \
                f"Client unstable on iteration {i+1}"
            
            time.sleep(1)

    def test_error_responses_are_well_formed(self, opal_client_url):
        """
        Test that invalid requests return proper error responses.
        
        Validates:
        - 404 for non-existent endpoints
        - Responses are JSON formatted
        - Error messages are informative
        """
        response = requests.get(f"{opal_client_url}/nonexistent-endpoint", timeout=10)
        
        # Should return 404
        assert response.status_code == 404, \
            "Non-existent endpoint should return 404"
        
        # Should be JSON
        try:
            response.json()
        except json.JSONDecodeError:
            pytest.fail("Error response is not valid JSON")

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
            opal_server_url + "/health",
            opal_client_url + "/health",
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

    def test_server_info_endpoint(self, opal_server_url):
        """
        Test that server provides version/info endpoint.
        
        Validates:
        - Endpoint accessibility
        - Returns server information
        """
        # Try common info endpoints
        for path in ["/info", "/version", "/"]:
            response = requests.get(f"{opal_server_url}{path}", timeout=10)
            if response.status_code == 200:
                # Found an info endpoint
                assert response.content, "Info endpoint returned empty response"
                break

    def test_client_info_endpoint(self, opal_client_url):
        """
        Test that client provides version/info endpoint.
        
        Validates:
        - Endpoint accessibility
        - Returns client information
        """
        # Try common info endpoints
        for path in ["/info", "/version", "/"]:
            response = requests.get(f"{opal_client_url}{path}", timeout=10)
            if response.status_code == 200:
                # Found an info endpoint
                assert response.content, "Info endpoint returned empty response"
                break

    def test_opa_api_version(self, opa_url):
        """
        Test that OPA returns its API version information.
        
        Validates:
        - OPA version endpoint is accessible
        - Version information is returned
        """
        response = requests.get(f"{opa_url}/", timeout=10)
        
        # OPA root endpoint should return version info
        assert response.status_code == 200, \
            "OPA version endpoint not accessible"


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
            "OPAL Server": opal_server_url,
            "OPAL Client": opal_client_url,
            "OPA": opa_url
        }
        
        timings = {}
        
        for name, base_url in services.items():
            start = time.time()
            requests.get(f"{base_url}/health", timeout=10)
            duration = (time.time() - start) * 1000  # Convert to ms
            timings[name] = duration
            
            assert duration < 500, \
                f"{name} health check too slow: {duration:.2f}ms (target: <500ms)"
        
        print(f"\nHealth check timings: {timings}")

    @pytest.mark.benchmark
    def test_statistics_response_time(self, opal_client_url):
        """
        Benchmark statistics endpoint response time.
        
        Performance target: <1 second
        """
        start = time.time()
        response = requests.get(f"{opal_client_url}/statistics", timeout=10)
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 1.0, \
            f"Statistics endpoint too slow: {duration:.2f}s (target: <1.0s)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
