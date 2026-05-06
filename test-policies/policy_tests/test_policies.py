#!/usr/bin/env python3
"""
Comprehensive test suite for generated Rego policies.
Tests policies against various data scenarios using OPA.
"""

import json
import subprocess
import pytest
from pathlib import Path
import tempfile
import shutil


class TestREGOPolicies:
    """Test suite for REGO policies."""
    
    @pytest.fixture(scope="session")
    def policies_dir(self):
        """Get the policies directory."""
        return Path(__file__).parent.parent / "policies"
    
    @pytest.fixture(scope="session")
    def test_data_dir(self):
        """Get the test data directory."""
        return Path(__file__).parent.parent / "test_data"
    
    @pytest.fixture(scope="session")
    def opa_executable(self):
        """Check if OPA executable is available."""
        try:
            result = subprocess.run(["opa", "version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return "opa"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("OPA executable not found. Install OPA to run tests.")
    
    def test_policies_exist(self, policies_dir):
        """Verify that all policy files exist."""
        policy_files = list(policies_dir.glob("*.rego"))
        assert len(policy_files) > 0, "No policy files found"
        assert len(policy_files) == 1000, f"Expected 1000 policies, found {len(policy_files)}"
    
    def test_test_data_exists(self, test_data_dir):
        """Verify that all test data files exist."""
        data_files = list(test_data_dir.glob("*.json"))
        assert len(data_files) > 0, "No test data files found"
        assert len(data_files) == 100, f"Expected 100 data files, found {len(data_files)}"
    
    def test_policies_have_valid_rego_syntax(self, policies_dir, opa_executable):
        """Test that all policies have valid Rego syntax."""
        policy_files = sorted(policies_dir.glob("*.rego"))
        
        failed_policies = []
        for policy_file in policy_files:
            try:
                result = subprocess.run(
                    [opa_executable, "check", str(policy_file)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    failed_policies.append({
                        "file": policy_file.name,
                        "error": result.stderr
                    })
            except subprocess.TimeoutExpired:
                failed_policies.append({
                    "file": policy_file.name,
                    "error": "Timeout during syntax check"
                })
        
        assert len(failed_policies) == 0, f"Syntax errors in policies: {failed_policies}"
    
    def test_policies_compile(self, policies_dir, opa_executable):
        """Test that all policies compile successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy all policies to temp directory
            for policy_file in policies_dir.glob("*.rego"):
                shutil.copy(policy_file, tmpdir)
            
            # Specify output file explicitly
            output_file = Path(tmpdir) / "policies.tar.gz"
            
            try:
                result = subprocess.run(
                    [opa_executable, "build", "-b", tmpdir, "-o", str(output_file)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                assert result.returncode == 0, f"Build failed: {result.stderr if result.stderr else result.stdout}"
            except subprocess.TimeoutExpired:
                pytest.fail("Policy compilation timed out")
    
    def test_policies_have_package_names(self, policies_dir):
        """Verify all policies have valid package names with 4+ levels."""
        policy_files = sorted(policies_dir.glob("*.rego"))
        failed_policies = []
        
        for policy_file in policy_files:
            with open(policy_file) as f:
                content = f.read()
            
            # Extract package statement
            for line in content.split("\n"):
                if line.strip().startswith("package "):
                    package_name = line.strip().replace("package ", "").strip()
                    depth = len(package_name.split("."))
                    
                    if depth < 4:
                        failed_policies.append({
                            "file": policy_file.name,
                            "package": package_name,
                            "depth": depth
                        })
                    break
        
        assert len(failed_policies) == 0, f"Policies with insufficient package depth: {failed_policies}"
    
    def test_sample_policy_evaluation(self, policies_dir, test_data_dir, opa_executable):
        """Test evaluation of sample policies against test data."""
        policy_files = sorted(policies_dir.glob("*.rego"))[:10]  # Test first 10
        test_data_files = sorted(test_data_dir.glob("*.json"))[:5]  # Use first 5 data files
        
        evaluation_results = []
        
        for policy_file in policy_files:
            for data_file in test_data_files:
                try:
                    with open(data_file) as f:
                        input_data = json.load(f)
                    
                    result = subprocess.run(
                        [opa_executable, "eval", "-d", str(policy_file), "-i", str(data_file),
                         "data"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    evaluation_results.append({
                        "policy": policy_file.name,
                        "data": data_file.name,
                        "success": result.returncode == 0
                    })
                except subprocess.TimeoutExpired:
                    evaluation_results.append({
                        "policy": policy_file.name,
                        "data": data_file.name,
                        "success": False
                    })
        
        # At least 80% of evaluations should succeed
        successful = sum(1 for r in evaluation_results if r["success"])
        success_rate = successful / len(evaluation_results) if evaluation_results else 0
        
        assert success_rate >= 0.8, f"Only {success_rate*100:.1f}% of evaluations succeeded"
    
    def test_policies_are_deterministic(self, policies_dir, test_data_dir, opa_executable):
        """Verify policies produce consistent results on repeated evaluations."""
        policy_files = sorted(policies_dir.glob("*.rego"))[:5]  # Test first 5
        test_data_files = sorted(test_data_dir.glob("*.json"))[:3]  # Use first 3 data files
        
        for policy_file in policy_files:
            for data_file in test_data_files:
                results = []
                
                for _ in range(2):
                    try:
                        result = subprocess.run(
                            [opa_executable, "eval", "-d", str(policy_file), "-i", str(data_file),
                             "data"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        results.append(result.stdout)
                    except subprocess.TimeoutExpired:
                        pytest.fail(f"Timeout evaluating {policy_file.name}")
                
                # Results should be identical
                assert results[0] == results[1], \
                    f"Non-deterministic results for {policy_file.name} with {data_file.name}"


class TestDataQuality:
    """Test suite for test data quality."""
    
    @pytest.fixture(scope="session")
    def test_data_dir(self):
        """Get the test data directory."""
        return Path(__file__).parent.parent / "test_data"
    
    def test_all_data_files_are_valid_json(self, test_data_dir):
        """Verify all test data files contain valid JSON."""
        data_files = sorted(test_data_dir.glob("*.json"))
        failed_files = []
        
        for data_file in data_files:
            try:
                with open(data_file) as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                failed_files.append({
                    "file": data_file.name,
                    "error": str(e)
                })
        
        assert len(failed_files) == 0, f"Invalid JSON files: {failed_files}"
    
    def test_data_files_have_required_fields(self, test_data_dir):
        """Verify test data files have expected structure."""
        data_files = sorted(test_data_dir.glob("*.json"))
        required_fields = {"test_id", "metadata", "users", "resources", "system"}
        
        invalid_files = []
        
        for data_file in data_files:
            with open(data_file) as f:
                data = json.load(f)
            
            missing_fields = required_fields - set(data.keys())
            if missing_fields:
                invalid_files.append({
                    "file": data_file.name,
                    "missing_fields": list(missing_fields)
                })
        
        assert len(invalid_files) == 0, f"Files missing required fields: {invalid_files}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
