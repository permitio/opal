# Migration Guide: Bash to PyTest E2E Framework

This guide helps you migrate from the bash-based E2E tests (`app-tests/run.sh`) to the new PyTest framework.

## Quick Start

### Old Way (Bash)
```bash
cd app-tests
./run.sh
```

### New Way (PyTest)
```bash
pytest tests/e2e/
```

## Key Differences

### 1. Test Execution

**Bash:**
- Single monolithic script
- Sequential execution only
- Limited error reporting
- Retry logic built into script

**PyTest:**
- Modular test classes and methods
- Can run tests individually or in parallel
- Detailed error messages and stack traces
- Retry via `pytest-rerunfailures` plugin

### 2. Environment Setup

**Bash:**
```bash
function generate_opal_keys {
  # Manual key generation
  # Manual token retrieval
}

function prepare_policy_repo {
  # Manual Gitea setup
  # Manual git operations
}
```

**PyTest:**
```python
@pytest.fixture(scope="session")
def opal_keys():
    # Automatic key generation
    # Automatic token retrieval
    yield keys
    # Automatic cleanup

@pytest.fixture(scope="session")
def policy_repo():
    # Automatic Gitea setup
    # Automatic git operations
    yield repo_info
    # Automatic cleanup
```

### 3. Test Structure

**Bash:**
```bash
function test_push_policy {
  echo "- Testing pushing policy $1"
  # Test logic
  check_clients_logged "PUT /v1/policies/$regofile -> 200"
}

# Call test
test_push_policy "something"
```

**PyTest:**
```python
class TestOPALPolicyUpdates:
    def test_push_policy_update(self, opal_environment, policy_repo):
        """Test pushing a new policy file."""
        # Test logic
        assert expected_log in logs
```

### 4. Assertions and Validation

**Bash:**
```bash
function check_clients_logged {
  echo "- Looking for msg '$1' in client's logs"
  compose logs --index 1 opal_client | grep -q "$1"
  compose logs --index 2 opal_client | grep -q "$1"
}
```

**PyTest:**
```python
result = compose_command("logs", "opal_client")
logs = result.stdout
assert "PUT /v1/policies/test.rego -> 200" in logs, \
    "Policy update not found in logs"
```

## Feature Mapping

### Bash Functions → PyTest Equivalents

| Bash Function | PyTest Equivalent | Location |
|---------------|-------------------|----------|
| `generate_opal_keys` | `opal_keys` fixture | `conftest.py` |
| `prepare_policy_repo` | `policy_repo` fixture | `conftest.py` |
| `compose` | `compose_command` fixture | `conftest.py` |
| `check_clients_logged` | Assertions in tests | `test_opal_e2e.py` |
| `check_no_error` | `test_no_critical_errors_in_logs` | `test_opal_e2e.py` |
| `test_push_policy` | `TestOPALPolicyUpdates` | `test_opal_e2e.py` |
| `test_data_publish` | `TestOPALDataUpdates` | `test_opal_e2e.py` |
| `test_statistics` | `TestOPALStatistics` | `test_opal_e2e.py` |
| `clean_up` | Fixture teardown | `conftest.py` |

### Test Coverage Comparison

| Test | Bash | PyTest |
|------|------|--------|
| Health checks | ✅ | ✅ |
| Client connection | ✅ | ✅ |
| Policy bundle | ✅ | ✅ |
| Static data | ✅ | ✅ |
| No errors | ✅ | ✅ |
| Single policy push | ✅ | ✅ |
| Multiple policy pushes | ✅ | ✅ |
| Single data update | ✅ | ✅ |
| Multiple data updates | ✅ | ✅ |
| Statistics | ✅ | ✅ |
| Broadcast restart | ✅ | ✅ |
| Recovery after restart | ✅ | ✅ |

## Running Specific Tests

### Bash
```bash
# Can't run individual tests easily
# Must modify script or comment out sections
./run.sh
```

### PyTest
```bash
# Run all tests
pytest tests/e2e/

# Run specific test class
pytest tests/e2e/test_opal_e2e.py::TestOPALHealth

# Run specific test
pytest tests/e2e/test_opal_e2e.py::TestOPALHealth::test_server_health

# Run tests matching pattern
pytest tests/e2e/ -k "policy"

# Run with verbose output
pytest tests/e2e/ -v

# Run with live output
pytest tests/e2e/ -s
```

## Debugging

### Bash
```bash
# Add set -x for debugging
set -x
./run.sh

# Check logs manually
docker compose -f docker-compose-app-tests.yml logs
```

### PyTest
```bash
# Run with verbose output and stop on first failure
pytest tests/e2e/ -vsx

# Run with full traceback
pytest tests/e2e/ --tb=long

# Run with pdb debugger on failure
pytest tests/e2e/ --pdb

# Run specific test with print output
pytest tests/e2e/test_opal_e2e.py::TestOPALHealth::test_server_health -s
```

## Retry Logic

### Bash
```bash
MAX_RETRIES=5
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  main && break
  RETRY_COUNT=$((RETRY_COUNT + 1))
done
```

### PyTest
```bash
# Install pytest-rerunfailures
pip install pytest-rerunfailures

# Run with retries
pytest tests/e2e/ --reruns 5 --reruns-delay 5
```

## Parallel Execution

### Bash
```bash
# Not supported
```

### PyTest
```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel
pytest tests/e2e/ -n auto

# Run with 4 workers
pytest tests/e2e/ -n 4
```

## CI/CD Integration

### Bash (GitHub Actions)
```yaml
- name: Run E2E tests
  run: |
    cd app-tests
    ./run.sh
```

### PyTest (GitHub Actions)
```yaml
- name: Run E2E tests
  run: |
    pytest tests/e2e/ -v --tb=short
```

## Adding New Tests

### Bash
```bash
# Add new function
function test_new_feature {
  echo "- Testing new feature"
  # Test logic
  check_clients_logged "expected log message"
}

# Call in main function
function main {
  # ... existing tests ...
  test_new_feature
}
```

### PyTest
```python
# Add new test method to appropriate class
class TestOPALNewFeature:
    def test_new_feature(self, opal_environment):
        """Test new feature."""
        # Test logic
        assert expected_condition, "Feature not working"
```

## Best Practices

### 1. Use Fixtures for Setup/Teardown
```python
@pytest.fixture
def my_setup():
    # Setup
    resource = create_resource()
    yield resource
    # Teardown
    cleanup_resource(resource)
```

### 2. Use Descriptive Test Names
```python
# Good
def test_client_receives_policy_update_after_git_push(self):
    pass

# Bad
def test_policy(self):
    pass
```

### 3. Add Docstrings
```python
def test_server_health(self):
    """
    Test that OPAL server health endpoints are accessible.
    
    This test verifies that at least one of the server's health
    endpoints returns a 200 status code.
    """
    pass
```

### 4. Use Clear Assertions
```python
# Good
assert response.status_code == 200, \
    f"Expected 200, got {response.status_code}"

# Bad
assert response.status_code == 200
```

### 5. Group Related Tests
```python
class TestOPALPolicyUpdates:
    """All tests related to policy updates."""
    
    def test_single_policy_update(self):
        pass
    
    def test_multiple_policy_updates(self):
        pass
```

## Troubleshooting

### Issue: Tests fail with "fixture not found"
**Solution:** Make sure `conftest.py` is in the correct location and fixtures are properly defined.

### Issue: Docker containers not cleaning up
**Solution:** Run cleanup manually:
```bash
cd app-tests
docker compose -f docker-compose-app-tests.yml down -v
rm -rf opal-tests-policy-repo temp-repo gitea-data git-repos .env
```

### Issue: Tests are slow
**Solution:** 
- Run tests in parallel: `pytest tests/e2e/ -n auto`
- Reduce timeout values in `conftest.py`
- Use session-scoped fixtures to avoid repeated setup

### Issue: Flaky tests
**Solution:**
- Use retries: `pytest tests/e2e/ --reruns 3`
- Increase sleep/timeout values
- Check for race conditions

## Benefits of PyTest Framework

1. **Better Maintainability**: Python code is easier to read and maintain than bash
2. **Modularity**: Reusable fixtures and helper functions
3. **Flexibility**: Run individual tests or test classes
4. **Better Debugging**: Detailed error messages and stack traces
5. **IDE Support**: Autocomplete, refactoring, and debugging tools
6. **Extensibility**: Easy to add new tests and features
7. **Parallel Execution**: Run tests faster with pytest-xdist
8. **Rich Ecosystem**: Many plugins available (coverage, HTML reports, etc.)
9. **Type Safety**: Type hints for better code quality
10. **Industry Standard**: PyTest is widely used and well-documented

## Next Steps

1. **Try the new framework**: Run `pytest tests/e2e/` and compare with bash script
2. **Add new tests**: Extend the framework with additional test cases
3. **Integrate with CI/CD**: Update your CI/CD pipeline to use PyTest
4. **Deprecate bash script**: Once confident, deprecate `app-tests/run.sh`

## Questions?

- Check the [README](README.md) for detailed documentation
- Review the [test code](test_opal_e2e.py) for examples
- Look at [fixtures](conftest.py) for setup/teardown logic

## Contributing

When contributing new tests:

1. Follow the existing structure and naming conventions
2. Add docstrings to all test methods
3. Use appropriate fixtures
4. Add clear assertion messages
5. Update documentation
6. Test your changes locally before submitting PR
