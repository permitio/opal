#!/usr/bin/env python3
"""
Script to generate 1000 Rego policies and 100 JSON data files for testing.
Each policy has at least 4 levels of package depth.
"""

import os
import json
import random
import string
from pathlib import Path


def create_policy_directories():
    """Create directory structure for policies."""
    base_path = Path(__file__).parent
    policies_dir = base_path / "policies"
    policies_dir.mkdir(exist_ok=True)
    
    tests_dir = base_path / "policy_tests"
    tests_dir.mkdir(exist_ok=True)
    
    data_dir = base_path / "test_data"
    data_dir.mkdir(exist_ok=True)
    
    return base_path, policies_dir, tests_dir, data_dir


def generate_package_hierarchy(policy_num):
    """Generate a deep package hierarchy (4+ levels)."""
    domains = ["security", "compliance", "access", "audit", "governance", "risk"]
    modules = ["authorization", "authentication", "validation", "enforcement", "monitoring"]
    components = ["user", "resource", "action", "context", "policy"]
    rules = ["allow", "deny", "check", "validate", "verify"]
    
    domain = random.choice(domains)
    module = random.choice(modules)
    component = random.choice(components)
    rule_type = random.choice(rules)
    
    # Ensure at least 4 levels
    package_path = f"{domain}.{module}.{component}.{rule_type}"
    
    # Add 5th level occasionally for more variety
    if random.random() > 0.6:
        suffixes = ["core", "utils", "helpers", "logic", "data"]
        package_path += f".{random.choice(suffixes)}"
    
    return package_path


def generate_rego_policy(policy_num, package_path):
    """Generate a sample Rego policy with realistic rules."""
    policy_name = f"policy_{policy_num:04d}"
    
    # Create various rule types with proper Rego v1 syntax
    rule_templates = [
        "default {name}_allowed = false",
        "{name}_allowed if {{\n    input.user.role == \"admin\"\n}}",
        "{name}_allowed if {{\n    input.user.active\n    input.resource.public\n}}",
        "{name}_denied if {{\n    input.action == \"delete\"\n    input.user.role != \"admin\"\n}}",
        "{name}_allowed if {{\n    data.policies.{dep}.enabled\n}}",
        "{name}_approved if {{\n    input.user.risk_score < 50\n    input.system.health > 0.8\n}}",
    ]
    
    # Select 2-4 rules randomly
    num_rules = random.randint(2, 4)
    selected_templates = random.sample(rule_templates, num_rules)
    
    rules = []
    for template in selected_templates:
        rule = template.format(name=policy_name, dep=package_path.split(".")[0])
        rules.append(rule)
    
    policy_content = f"""package {package_path}.{policy_name}

# Auto-generated policy {policy_num}
# Package: {package_path}

# Metadata
metadata := {{
    "policy_id": "{policy_num:04d}",
    "version": "1.0",
    "created": "2026-05-06",
}}

# Rules
{chr(10).join(rules)}

# Utility function for user info
get_user_info if {{
    user := {{
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }}
}}
"""
    
    return policy_content


def generate_json_data_files(num_files, data_dir):
    """Generate JSON test data files with varied structures."""
    for i in range(num_files):
        file_num = i + 1
        filename = data_dir / f"testdata_{file_num:03d}.json"
        
        # Create varied data structures
        data = {
            "test_id": file_num,
            "metadata": {
                "environment": random.choice(["dev", "staging", "prod"]),
                "region": random.choice(["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1"]),
                "version": f"1.{random.randint(0, 5)}.{random.randint(0, 20)}",
            },
            "users": [
                {
                    "id": f"user_{j:03d}",
                    "name": f"User {j}",
                    "role": random.choice(["admin", "user", "viewer", "editor", "auditor"]),
                    "active": random.choice([True, False]),
                    "risk_score": random.randint(0, 100),
                }
                for j in range(random.randint(1, 10))
            ],
            "resources": [
                {
                    "id": f"res_{k:03d}",
                    "type": random.choice(["file", "database", "api", "service", "bucket"]),
                    "public": random.choice([True, False]),
                    "owner_id": f"user_{random.randint(0, 100):03d}",
                    "sensitivity": random.choice(["public", "internal", "confidential", "secret"]),
                }
                for k in range(random.randint(1, 5))
            ],
            "system": {
                "health": round(random.uniform(0.5, 1.0), 2),
                "load": round(random.uniform(0.0, 100.0), 2),
                "uptime_days": random.randint(1, 365),
            },
            "policies": {
                "security": {"enabled": random.choice([True, False])},
                "compliance": {"enabled": random.choice([True, False])},
                "access": {"enabled": random.choice([True, False])},
                "audit": {"enabled": random.choice([True, False])},
            }
        }
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"Generated test data file {file_num:03d}/{num_files}")


def generate_policies(num_policies, policies_dir):
    """Generate all Rego policies."""
    for i in range(1, num_policies + 1):
        package_path = generate_package_hierarchy(i)
        policy_content = generate_rego_policy(i, package_path)
        
        filename = policies_dir / f"policy_{i:04d}.rego"
        
        with open(filename, "w") as f:
            f.write(policy_content)
        
        if i % 100 == 0:
            print(f"Generated {i}/{num_policies} policies")
    
    print(f"Generated {num_policies} policies in {policies_dir}")


def generate_test_suite(policies_dir, tests_dir, data_dir):
    """Generate a pytest-based test suite."""
    test_content = '''#!/usr/bin/env python3
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
            
            try:
                result = subprocess.run(
                    [opa_executable, "build", "-b", tmpdir],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                assert result.returncode == 0, f"Build failed: {result.stderr}"
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
            for line in content.split("\\n"):
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
                assert results[0] == results[1], \\
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
'''
    
    test_file = tests_dir / "test_policies.py"
    with open(test_file, "w") as f:
        f.write(test_content)
    
    # Make it executable
    os.chmod(test_file, 0o755)
    print(f"Generated test suite at {test_file}")


def generate_test_runner(base_path):
    """Generate a bash script to run all tests."""
    runner_content = '''#!/bin/bash
# Test runner script for OPAL test policies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICIES_DIR="$SCRIPT_DIR/policies"
TEST_DATA_DIR="$SCRIPT_DIR/test_data"
TESTS_DIR="$SCRIPT_DIR/policy_tests"

echo "========================================"
echo "OPAL Test Policies - Local Test Runner"
echo "========================================"
echo ""

# Check if OPA is installed
if ! command -v opa &> /dev/null; then
    echo "⚠️  Warning: OPA is not installed. Some tests will be skipped."
    echo "   Install OPA from: https://www.openpolicyagent.org/docs/latest/#running-opa"
    echo ""
fi

# Count files
POLICY_COUNT=$(find "$POLICIES_DIR" -name "*.rego" | wc -l)
DATA_COUNT=$(find "$TEST_DATA_DIR" -name "*.json" | wc -l)

echo "📊 Generated Assets:"
echo "   Policies: $POLICY_COUNT"
echo "   Test Data Files: $DATA_COUNT"
echo ""

# Run syntax checks with OPA if available
if command -v opa &> /dev/null; then
    echo "✓ Running OPA syntax checks..."
    for policy in "$POLICIES_DIR"/*.rego; do
        if ! opa check "$policy" > /dev/null 2>&1; then
            echo "✗ Syntax error in $(basename "$policy")"
            exit 1
        fi
    done
    echo "✓ All policies have valid Rego syntax"
    echo ""
fi

# Run pytest if available
if command -v pytest &> /dev/null; then
    echo "✓ Running pytest test suite..."
    cd "$TESTS_DIR"
    pytest test_policies.py -v --tb=short
else
    echo "⚠️  pytest not found. Install with: pip install pytest"
    echo "   Then run: pytest policy_tests/test_policies.py -v"
fi

echo ""
echo "✓ Test run complete!"
'''
    
    runner_file = base_path / "run_tests.sh"
    with open(runner_file, "w") as f:
        f.write(runner_content)
    
    os.chmod(runner_file, 0o755)
    print(f"Generated test runner at {runner_file}")


def generate_readme(base_path):
    """Generate a comprehensive README."""
    readme_content = '''# OPAL Test Policies - Large Scale Generation

This directory contains auto-generated Rego policies and test data for comprehensive policy testing.

## Generated Assets

- **1000 Rego Policies**: Organized with 4+ level package hierarchies
  - Location: `policies/policy_*.rego`
  - Package structure: `domain.module.component.rule_type[.suffix]`
  
- **100 JSON Test Data Files**: Diverse test scenarios
  - Location: `test_data/testdata_*.json`
  - Contains: users, resources, system state, policies metadata

- **Comprehensive Test Suite**: Pytest-based testing
  - Location: `policy_tests/test_policies.py`
  - Tests syntax, compilation, evaluation, and data quality

## Requirements

### Minimal (for generation only)
- Python 3.7+
- pytest (for running tests)

### Full (for complete testing)
- OPA (Open Policy Agent) 0.45+
  - Install: `brew install opa` (macOS) or see https://www.openpolicyagent.org/docs/latest/#running-opa

## Getting Started

### 1. Generate Policies and Data

The policies and data are already generated. To regenerate:

\`\`\`bash
python3 generate_policies.py
\`\`\`

### 2. Run Tests Locally

#### Option A: Automated Test Runner
\`\`\`bash
./run_tests.sh
\`\`\`

#### Option B: Manual Testing with pytest
\`\`\`bash
# Install dependencies
pip install pytest

# Run all tests
pytest policy_tests/test_policies.py -v

# Run specific test class
pytest policy_tests/test_policies.py::TestREGOPolicies -v

# Run with coverage
pytest policy_tests/test_policies.py --cov=. --cov-report=html
\`\`\`

#### Option C: Manual Testing with OPA
\`\`\`bash
# Check syntax of all policies
for f in policies/*.rego; do
  opa check "$f" || echo "Error in $f"
done

# Build all policies
opa build -b policies/

# Evaluate a specific policy with data
opa eval -d policies/policy_0001.rego -i test_data/testdata_001.json "data"

# Run policy tests
opa test policies/ -v
\`\`\`

## Directory Structure

```
test-policies/
├── policies/                    # 1000 generated Rego policies
│   ├── policy_0001.rego
│   ├── policy_0002.rego
│   └── ...
├── test_data/                   # 100 JSON test data files
│   ├── testdata_001.json
│   ├── testdata_002.json
│   └── ...
├── policy_tests/                # Test suite
│   └── test_policies.py
├── generate_policies.py         # Generation script
├── run_tests.sh                 # Test runner
└── README.md                    # This file
```

## Test Coverage

### TestREGOPolicies
- ✓ Verify 1000 policies exist
- ✓ Verify 100 test data files exist
- ✓ Check valid Rego syntax for all policies
- ✓ Verify policies compile successfully
- ✓ Validate package names have 4+ levels
- ✓ Test sample policies against test data
- ✓ Verify deterministic evaluation results

### TestDataQuality
- ✓ Validate JSON format of all data files
- ✓ Check required fields in test data

## Package Hierarchy

All 1000 policies follow a deep package structure with at least 4 levels:

```
package domain.module.component.rule_type[.suffix]

Examples:
- security.authorization.user.allow.core
- compliance.validation.resource.deny.utils
- access.enforcement.action.check.helpers
- audit.monitoring.context.verify.logic
- governance.policy.data.validate
- risk.authentication.policy.enforce
```

## Test Data Structure

Each test data file includes:

```json
{
  "test_id": 1,
  "metadata": {
    "environment": "dev|staging|prod",
    "region": "us-east-1|us-west-2|eu-west-1|ap-northeast-1",
    "version": "1.x.y"
  },
  "users": [
    {
      "id": "user_001",
      "role": "admin|user|viewer|editor|auditor",
      "active": true|false,
      "risk_score": 0-100
    }
  ],
  "resources": [
    {
      "id": "res_001",
      "type": "file|database|api|service|bucket",
      "public": true|false,
      "sensitivity": "public|internal|confidential|secret"
    }
  ],
  "system": {
    "health": 0.0-1.0,
    "load": 0.0-100.0,
    "uptime_days": 0-365
  },
  "policies": {
    "security": {"enabled": true|false},
    "compliance": {"enabled": true|false},
    "access": {"enabled": true|false},
    "audit": {"enabled": true|false}
  }
}
```

## Troubleshooting

### OPA not found
Install OPA from: https://www.openpolicyagent.org/docs/latest/#running-opa

**macOS:**
\`\`\`bash
brew install opa
\`\`\`

**Linux:**
\`\`\`bash
curl -L -o opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64
chmod +x opa
sudo mv opa /usr/local/bin
\`\`\`

### pytest not found
\`\`\`bash
pip install pytest
\`\`\`

### Policy compilation timeout
- Reduce number of policies in test by modifying `policy_tests/test_policies.py`
- Increase OPA memory allocation

## Continuous Integration

Example GitHub Actions workflow:

\`\`\`yaml
name: Policy Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - uses: open-policy-agent/setup-opa@v1
      - name: Install pytest
        run: pip install pytest
      - name: Run tests
        run: cd test-policies && pytest policy_tests/test_policies.py -v
\`\`\`

## Performance Notes

- Generating 1000 policies: ~2-5 seconds
- Generating 100 data files: ~1 second
- Syntax checking all policies: ~30-60 seconds (with OPA)
- Full test suite execution: ~2-5 minutes (depends on system)

## License

Auto-generated test assets. Use as needed for testing and development.
'''
    
    readme_file = base_path / "GENERATED_README.md"
    with open(readme_file, "w") as f:
        f.write(readme_content)
    print(f"Generated README at {readme_file}")


def main():
    """Main generation workflow."""
    print("🚀 Starting OPAL Policy Generation")
    print()
    
    base_path, policies_dir, tests_dir, data_dir = create_policy_directories()
    
    print("📝 Generating 1000 policies with 4+ level package hierarchy...")
    generate_policies(1000, policies_dir)
    print()
    
    print("📊 Generating 100 JSON test data files...")
    generate_json_data_files(100, data_dir)
    print()
    
    print("🧪 Generating test suite...")
    generate_test_suite(policies_dir, tests_dir, data_dir)
    print()
    
    print("📜 Generating test runner script...")
    generate_test_runner(base_path)
    print()
    
    print("📖 Generating documentation...")
    generate_readme(base_path)
    print()
    
    print("✅ Generation complete!")
    print()
    print("📁 Generated structure:")
    print(f"   Policies: {policies_dir}")
    print(f"   Test Data: {data_dir}")
    print(f"   Tests: {tests_dir}")
    print()
    print("🚀 To run tests:")
    print(f"   ./run_tests.sh")
    print()


if __name__ == "__main__":
    main()
