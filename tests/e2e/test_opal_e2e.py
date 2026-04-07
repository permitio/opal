"""
End-to-end tests for OPAL Server and Client.

This module contains comprehensive E2E tests that verify:
- OPAL server and client health and connectivity
- Policy updates via git push
- Data updates via API
- Statistics and monitoring
- Broadcast channel resilience
"""

import subprocess
import time
from pathlib import Path
from typing import Dict

import pytest
import requests


class TestOPALHealth:
    """Test OPAL server and client health endpoints."""
    
    def test_server_health(self, opal_environment):
        """Test that OPAL server health endpoints are accessible."""
        server_paths = ["/healthcheck", "/", "/healthz", "/ready"]
        
        for path in server_paths:
            try:
                response = requests.get(f"http://localhost:7002{path}", timeout=3)
                if response.status_code == 200:
                    print(f"✅ OPAL Server is ready on {path}")
                    return
            except requests.RequestException:
                continue
        
        pytest.fail("❌ OPAL Server health check failed on all endpoints")
    
    def test_client_health(self, opal_environment):
        """Test that OPAL client health endpoints are accessible."""
        client_paths = ["/healthcheck", "/healthy", "/", "/ready"]
        
        for path in client_paths:
            try:
                response = requests.get(f"http://localhost:7000{path}", timeout=3)
                if response.status_code == 200:
                    print(f"✅ OPAL Client is ready on {path}")
                    return
            except requests.RequestException:
                continue
        
        pytest.fail("❌ OPAL Client health check failed on all endpoints")


class TestOPALConnectivity:
    """Test OPAL server-client connectivity."""
    
    def test_client_server_connection(self, opal_environment, compose_command):
        """Test that OPAL clients are connected to the server."""
        print("\n- Checking if clients are connected to server")
        
        timeout = 240
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get("http://localhost:7002/statistics", timeout=4)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check various possible response formats
                    if data.get("client_is_connected") is True:
                        print("✅ Client connected to server")
                        return
                    
                    connected_clients = (
                        data.get("connected_clients") or 
                        data.get("clients")
                    )
                    
                    if isinstance(connected_clients, list) and len(connected_clients) > 0:
                        print("✅ Client connected to server")
                        return
                    
                    if isinstance(connected_clients, dict) and len(connected_clients) > 0:
                        print("✅ Client connected to server")
                        return
                    
                    if isinstance(connected_clients, int) and connected_clients > 0:
                        print("✅ Client connected to server")
                        return
            except requests.RequestException:
                pass
            
            time.sleep(2)
        
        pytest.fail("❌ Client never connected to server")
    
    def test_clients_received_policy_bundle(self, opal_environment, compose_command):
        """Test that clients received the initial policy bundle."""
        print("\n- Checking if clients received policy bundle")
        
        result = compose_command("logs", "opal_client")
        logs = result.stdout
        
        assert "Got policy bundle" in logs, "Clients did not receive policy bundle"
        print("✅ Clients received policy bundle")
    
    def test_clients_connected_to_pubsub(self, opal_environment, compose_command):
        """Test that clients are connected to the PubSub server."""
        print("\n- Checking if clients connected to PubSub")
        
        result = compose_command("logs", "opal_client")
        logs = result.stdout
        
        assert "Connected to PubSub server" in logs, "Clients not connected to PubSub"
        print("✅ Clients connected to PubSub")
    
    def test_clients_loaded_static_data(self, opal_environment, compose_command):
        """Test that clients loaded static data."""
        print("\n- Checking if clients loaded static data")
        
        result = compose_command("logs", "opal_client")
        logs = result.stdout
        
        assert "PUT /v1/data/static -> 204" in logs, "Clients did not load static data"
        print("✅ Clients loaded static data")
    
    def test_no_critical_errors_in_logs(self, opal_environment, compose_command):
        """Test that there are no CRITICAL errors in the logs."""
        print("\n- Checking logs for CRITICAL errors")
        
        result = compose_command("logs")
        logs = result.stdout
        
        assert "CRITICAL" not in logs, "Found CRITICAL errors in logs"
        print("✅ No CRITICAL errors in logs")


class TestOPALPolicyUpdates:
    """Test OPAL policy update functionality."""
    
    def test_push_policy_update(
        self,
        opal_environment,
        compose_command,
        policy_repo: Dict[str, str],
        opal_keys: Dict[str, str]
    ):
        """Test pushing a new policy file and verifying it's received by clients."""
        print("\n- Testing policy push: test_policy")
        
        policy_name = "test_policy"
        policy_file = f"{policy_name}.rego"
        repo_path = Path(policy_repo["path"])
        
        # Create and commit new policy
        policy_path = repo_path / policy_file
        with open(policy_path, "w") as f:
            f.write(f"package {policy_name}\n")
        
        subprocess.run(["git", "add", policy_file], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Add {policy_file}"],
            cwd=repo_path,
            check=True
        )
        subprocess.run(
            ["git", "push", "origin", policy_repo["branch"]],
            cwd=repo_path,
            check=True
        )
        
        # Trigger webhook
        webhook_data = {
            "gitEvent": "git.push",
            "repository": {
                "git_url": policy_repo["webhook_url"]
            }
        }
        
        requests.post(
            "http://localhost:7002/webhook",
            headers={
                "Content-Type": "application/json",
                "x-webhook-token": "xxxxx"
            },
            json=webhook_data,
            timeout=5
        )
        
        # Wait and check logs
        time.sleep(5)
        
        result = compose_command("logs", "opal_client")
        logs = result.stdout
        
        expected_log = f"PUT /v1/policies/{policy_file} -> 200"
        assert expected_log in logs, f"Policy update not found in logs: {expected_log}"
        print(f"✅ Policy {policy_file} successfully pushed to clients")
    
    def test_multiple_policy_updates(
        self,
        opal_environment,
        compose_command,
        policy_repo: Dict[str, str],
        opal_keys: Dict[str, str]
    ):
        """Test pushing multiple policy files."""
        policies = ["policy_one", "policy_two", "policy_three"]
        repo_path = Path(policy_repo["path"])
        
        for policy_name in policies:
            print(f"\n- Testing policy push: {policy_name}")
            
            policy_file = f"{policy_name}.rego"
            policy_path = repo_path / policy_file
            
            with open(policy_path, "w") as f:
                f.write(f"package {policy_name}\n")
            
            subprocess.run(["git", "add", policy_file], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"Add {policy_file}"],
                cwd=repo_path,
                check=True
            )
            subprocess.run(
                ["git", "push", "origin", policy_repo["branch"]],
                cwd=repo_path,
                check=True
            )
            
            # Trigger webhook
            webhook_data = {
                "gitEvent": "git.push",
                "repository": {
                    "git_url": policy_repo["webhook_url"]
                }
            }
            
            requests.post(
                "http://localhost:7002/webhook",
                headers={
                    "Content-Type": "application/json",
                    "x-webhook-token": "xxxxx"
                },
                json=webhook_data,
                timeout=5
            )
            
            time.sleep(5)
            
            result = compose_command("logs", "opal_client")
            logs = result.stdout
            
            expected_log = f"PUT /v1/policies/{policy_file} -> 200"
            assert expected_log in logs, f"Policy update not found: {expected_log}"
            print(f"✅ Policy {policy_file} successfully pushed")


class TestOPALDataUpdates:
    """Test OPAL data update functionality."""
    
    def test_publish_data_update(
        self,
        opal_environment,
        compose_command,
        opal_keys: Dict[str, str]
    ):
        """Test publishing a data update via the OPAL server API."""
        print("\n- Testing data publish for user: alice")
        
        user = "alice"
        data_update = {
            "entries": [{
                "url": "https://api.country.is/23.54.6.78",
                "config": {},
                "topics": ["policy_data"],
                "dst_path": f"/users/{user}/location",
                "save_method": "PUT"
            }]
        }
        
        response = requests.post(
            "http://localhost:7002/data/config",
            headers={
                "Authorization": f"Bearer {opal_keys['datasource_token']}",
                "Content-Type": "application/json"
            },
            json=data_update,
            timeout=5
        )
        
        response.raise_for_status()
        time.sleep(5)
        
        result = compose_command("logs", "opal_client")
        logs = result.stdout
        
        expected_log = f"PUT /v1/data/users/{user}/location -> 204"
        assert expected_log in logs, f"Data update not found in logs: {expected_log}"
        print(f"✅ Data update for user {user} successfully published")
    
    def test_multiple_data_updates(
        self,
        opal_environment,
        compose_command,
        opal_keys: Dict[str, str]
    ):
        """Test publishing multiple data updates."""
        users = ["bob", "charlie", "david"]
        
        for user in users:
            print(f"\n- Testing data publish for user: {user}")
            
            data_update = {
                "entries": [{
                    "url": "https://api.country.is/23.54.6.78",
                    "config": {},
                    "topics": ["policy_data"],
                    "dst_path": f"/users/{user}/location",
                    "save_method": "PUT"
                }]
            }
            
            response = requests.post(
                "http://localhost:7002/data/config",
                headers={
                    "Authorization": f"Bearer {opal_keys['datasource_token']}",
                    "Content-Type": "application/json"
                },
                json=data_update,
                timeout=5
            )
            
            response.raise_for_status()
            time.sleep(5)
            
            result = compose_command("logs", "opal_client")
            logs = result.stdout
            
            expected_log = f"PUT /v1/data/users/{user}/location -> 204"
            assert expected_log in logs, f"Data update not found: {expected_log}"
            print(f"✅ Data update for user {user} successfully published")


class TestOPALStatistics:
    """Test OPAL statistics and monitoring."""
    
    def test_statistics_endpoint(
        self,
        opal_environment,
        opal_keys: Dict[str, str]
    ):
        """Test that the statistics endpoint returns correct information."""
        print("\n- Testing statistics endpoint")
        
        # Test both server ports
        for port in [7002, 7003]:
            # Retry multiple times as different workers might respond
            for _ in range(8):
                try:
                    response = requests.get(
                        f"http://localhost:{port}/stats",
                        headers={
                            "Authorization": f"Bearer {opal_keys['datasource_token']}"
                        },
                        timeout=3
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Check for expected statistics
                        if (data.get("client_count") == 2 and 
                            data.get("server_count") == 2):
                            print(f"✅ Statistics endpoint working on port {port}")
                            break
                except requests.RequestException:
                    pass
                
                time.sleep(0.5)


class TestOPALResilience:
    """Test OPAL resilience and recovery."""
    
    def test_broadcast_channel_restart(
        self,
        opal_environment,
        compose_command,
        policy_repo: Dict[str, str],
        opal_keys: Dict[str, str]
    ):
        """Test that OPAL recovers after broadcast channel restart."""
        print("\n- Testing broadcast channel disconnection and recovery")
        
        # Restart broadcast channel
        compose_command("restart", "broadcast_channel")
        time.sleep(10)
        
        # Test data update after restart
        user = "eve"
        data_update = {
            "entries": [{
                "url": "https://api.country.is/23.54.6.78",
                "config": {},
                "topics": ["policy_data"],
                "dst_path": f"/users/{user}/location",
                "save_method": "PUT"
            }]
        }
        
        response = requests.post(
            "http://localhost:7002/data/config",
            headers={
                "Authorization": f"Bearer {opal_keys['datasource_token']}",
                "Content-Type": "application/json"
            },
            json=data_update,
            timeout=5
        )
        
        response.raise_for_status()
        time.sleep(5)
        
        result = compose_command("logs", "opal_client")
        logs = result.stdout
        
        expected_log = f"PUT /v1/data/users/{user}/location -> 204"
        assert expected_log in logs, "Data update failed after broadcast restart"
        print("✅ OPAL recovered after broadcast channel restart")
        
        # Test policy update after restart
        policy_name = "recovery_test"
        policy_file = f"{policy_name}.rego"
        repo_path = Path(policy_repo["path"])
        
        policy_path = repo_path / policy_file
        with open(policy_path, "w") as f:
            f.write(f"package {policy_name}\n")
        
        subprocess.run(["git", "add", policy_file], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Add {policy_file}"],
            cwd=repo_path,
            check=True
        )
        subprocess.run(
            ["git", "push", "origin", policy_repo["branch"]],
            cwd=repo_path,
            check=True
        )
        
        webhook_data = {
            "gitEvent": "git.push",
            "repository": {
                "git_url": policy_repo["webhook_url"]
            }
        }
        
        requests.post(
            "http://localhost:7002/webhook",
            headers={
                "Content-Type": "application/json",
                "x-webhook-token": "xxxxx"
            },
            json=webhook_data,
            timeout=5
        )
        
        time.sleep(5)
        
        result = compose_command("logs", "opal_client")
        logs = result.stdout
        
        expected_log = f"PUT /v1/policies/{policy_file} -> 200"
        assert expected_log in logs, "Policy update failed after broadcast restart"
        print("✅ Policy updates working after broadcast channel restart")
