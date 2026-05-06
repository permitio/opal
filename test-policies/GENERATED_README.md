# OPAL Test Policies - Large Scale Generation

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
