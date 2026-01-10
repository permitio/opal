# Advanced E2E Testing Guide

This guide covers advanced testing scenarios and best practices for the OPAL E2E test suite.

## Test Organization

The test suite is organized into logical test classes:

### Test Classes

1. **TestHealthChecks**: Basic health and availability tests
2. **TestConnectivity**: Service communication and connectivity
3. **TestPolicyOperations**: Policy loading and execution
4. **TestDataSynchronization**: Data sync between components
5. **TestSystemReliability**: Error handling and stability
6. **TestEndpointValidation**: API contract testing
7. **TestPerformance**: Performance benchmarks

## Running Tests

### Basic Execution

```bash
# Run all tests
pytest -v

# Run specific test class
pytest test_e2e.py::TestHealthChecks -v

# Run specific test
pytest test_e2e.py::TestHealthChecks::test_opal_server_health -v

# Run with markers
pytest -m benchmark -v
pytest -m "not slow" -v
```

### Advanced Options

```bash
# Parallel execution (faster)
pytest -n auto

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Verbose output with full traceback
pytest -vv --tb=long

# Quiet mode (minimal output)
pytest -q

# Only show failed tests summary
pytest --tb=no -q
```

### Coverage Reports

```bash
# Generate coverage report
pytest --cov=. --cov-report=term-missing

# HTML coverage report
pytest --cov=. --cov-report=html
# Open htmlcov/index.html in browser

# XML coverage (for CI/CD)
pytest --cov=. --cov-report=xml
```

### Test Reports

```bash
# HTML report
pytest --html=report.html --self-contained-html

# JSON report
pytest --json-report --json-report-file=report.json

# JUnit XML (for CI/CD)
pytest --junitxml=junit.xml
```

## Writing New Tests

### Test Structure

```python
class TestMyFeature:
    """Test suite for my feature."""
    
    def test_basic_functionality(self, opal_client_url):
        """
        Test basic functionality.
        
        Validates:
        - Expected behavior
        - Edge cases
        """
        # Arrange
        url = f"{opal_client_url}/my-endpoint"
        
        # Act
        response = requests.get(url, timeout=10)
        
        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
```

### Using Fixtures

```python
def test_with_multiple_fixtures(
    self, 
    opal_server_url, 
    opal_client_url, 
    wait_for,
    make_request
):
    """Test using multiple fixtures."""
    
    # Use wait_for helper
    connected = wait_for(
        lambda: make_request(f"{opal_client_url}/health").status_code == 200,
        timeout=30,
        description="Client to be ready"
    )
    assert connected
```

### Adding Custom Markers

```python
@pytest.mark.slow
@pytest.mark.benchmark
def test_performance_intensive_operation(self):
    """This test takes a long time."""
    # ... test code
```

Then run: `pytest -m slow` or `pytest -m "not slow"`

## Best Practices

### 1. Clear Test Names

```python
# Good
def test_client_connects_to_server_within_30_seconds(self):
    pass

# Bad
def test_connection(self):
    pass
```

### 2. Descriptive Assertions

```python
# Good
assert response.status_code == 200, \
    f"Health check failed with status {response.status_code}, body: {response.text}"

# Bad
assert response.status_code == 200
```

### 3. Proper Test Isolation

```python
# Each test should be independent
def test_feature_a(self):
    # Don't rely on test_feature_b running first
    pass

def test_feature_b(self):
    # Don't modify global state
    pass
```

### 4. Use Timeouts

```python
# Always use timeouts for network requests
response = requests.get(url, timeout=10)

# Use retry logic for flaky operations
for attempt in range(3):
    try:
        response = requests.get(url, timeout=5)
        break
    except requests.exceptions.Timeout:
        if attempt == 2:
            raise
        time.sleep(2)
```

### 5. Test Data Management

```python
# Use fixtures for test data
@pytest.fixture
def sample_policy():
    return {
        "rule": "allow",
        "effect": "permit"
    }

def test_policy_validation(self, sample_policy):
    # Use fixture data
    assert validate_policy(sample_policy)
```

## Debugging Tests

### Running in Debug Mode

```bash
# Show print statements
pytest -s

# Drop into debugger on failure
pytest --pdb

# Drop into debugger at start of test
pytest --trace
```

### Logging

```python
import logging

def test_with_logging(self):
    logging.info("Starting test")
    logging.debug("Debug information")
    # Test code
    logging.info("Test complete")
```

### Inspecting Docker Containers

```bash
# While tests are running in another terminal
docker ps

# View logs
docker logs opal_e2e_tests_opal_server_1

# Execute commands in container
docker exec -it opal_e2e_tests_opal_server_1 sh
```

### Keep Containers Running

```bash
# Don't cleanup containers after tests
pytest --keep-containers

# Then inspect them manually
docker ps
docker logs <container-id>
```

## Performance Testing

### Benchmark Tests

```python
@pytest.mark.benchmark
def test_api_response_time(self, benchmark, opal_client_url):
    """Benchmark API response time."""
    
    def api_call():
        return requests.get(f"{opal_client_url}/health")
    
    result = benchmark(api_call)
    assert result.status_code == 200
```

### Load Testing

```python
def test_concurrent_requests(self, opal_server_url):
    """Test system under concurrent load."""
    import concurrent.futures
    
    def make_request():
        return requests.get(f"{opal_server_url}/health")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(100)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    assert all(r.status_code == 200 for r in results)
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd e2e-tests
          pip install -r requirements.txt
      
      - name: Run tests
        run: |
          cd e2e-tests
          pytest --junitxml=junit.xml --cov=. --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./e2e-tests/coverage.xml
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: e2e-tests/junit.xml
```

### GitLab CI Example

```yaml
e2e-tests:
  stage: test
  image: python:3.11
  services:
    - docker:dind
  before_script:
    - cd e2e-tests
    - pip install -r requirements.txt
  script:
    - pytest --junitxml=junit.xml --cov=. --cov-report=term
  coverage: '/TOTAL.*\s+(\d+%)$/'
  artifacts:
    when: always
    reports:
      junit: e2e-tests/junit.xml
      coverage_report:
        coverage_format: cobertura
        path: e2e-tests/coverage.xml
```

## Troubleshooting Common Issues

### Issue: Tests hang indefinitely

**Cause**: Service not starting properly

**Solution**:
```bash
# Check container logs
docker logs opal_e2e_tests_opal_server_1

# Verify services are running
docker ps

# Check resource usage
docker stats
```

### Issue: Port conflicts

**Cause**: Ports already in use

**Solution**:
```bash
# Find process using port
lsof -i :7002  # Mac/Linux
netstat -ano | findstr :7002  # Windows

# Kill process or change ports in docker-compose.yml
```

### Issue: Flaky tests

**Cause**: Race conditions or timing issues

**Solution**:
```python
# Add retries and better waits
def test_flaky_operation(self, wait_for):
    success = wait_for(
        lambda: check_condition(),
        timeout=30,
        interval=1,
        description="Condition to be met"
    )
    assert success
```

### Issue: Out of memory

**Cause**: Docker resource limits

**Solution**:
```bash
# Increase Docker memory
# Docker Desktop -> Settings -> Resources -> Memory

# Or cleanup unused containers
docker system prune -a
```

## Tips and Tricks

### 1. Quick Smoke Test

```bash
# Run only critical tests
pytest -m critical --maxfail=1
```

### 2. Test Specific Scenario

```bash
# Use -k to match test names
pytest -k "health" -v
pytest -k "connect or sync" -v
```

### 3. Regenerate Failed Tests

```bash
# First run
pytest

# Re-run only failures
pytest --lf

# Re-run failures first, then all
pytest --ff
```

### 4. Custom Test Order

```python
# Install pytest-ordering
# pip install pytest-ordering

@pytest.mark.order(1)
def test_first():
    pass

@pytest.mark.order(2)
def test_second():
    pass
```

### 5. Parameterized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("http://example.com", 200),
    ("http://invalid", 404),
])
def test_url_validation(self, input, expected):
    # Test runs twice with different inputs
    assert check_url(input) == expected
```

## Resources

- [PyTest Documentation](https://docs.pytest.org/)
- [pytest-docker Plugin](https://github.com/avast/pytest-docker)
- [Requests Documentation](https://requests.readthedocs.io/)
- [OPAL Documentation](https://docs.opal.ac)

## Contributing

When adding new tests:

1. Follow existing patterns and structure
2. Add clear docstrings
3. Use appropriate markers
4. Include validation steps in docstring
5. Add to relevant test class
6. Update this guide if adding new patterns

## Questions?

- Open an issue on GitHub
- Join the OPAL Slack community
- Check existing tests for examples
