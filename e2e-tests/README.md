# OPAL End-to-End Tests

This directory contains the end-to-end (E2E) test suite for OPAL, built with PyTest and Docker Compose. These tests verify the complete integration between OPAL Server, OPAL Client, and OPA (Open Policy Agent).

## Overview

The E2E test framework provides:
- **Automated Docker Setup**: Automatically spins up OPAL Server, OPAL Client, and OPA using Docker Compose
- **Health Checks**: Verifies all services are running and responsive
- **Connection Testing**: Ensures OPAL Client successfully connects to OPAL Server
- **Log Validation**: Checks for errors and critical alerts in service logs
- **Statistics API Validation**: Confirms successful policy and data updates

## Prerequisites

- **Python 3.9+** installed
- **Docker** and **Docker Compose** installed and running
- **Git** (for cloning the repository)

## Quick Start

### Option 1: Using Make (Recommended)

From the project root directory:

```bash
# Run E2E tests (automatically creates venv if needed)
make test-e2e
```

### Option 2: Manual Setup

1. **Create a virtual environment** (if not already created):
   ```bash
   cd e2e-tests
   python -m venv .venv
   ```

2. **Activate the virtual environment**:
   - **Linux/Mac**:
     ```bash
     source .venv/bin/activate
     ```
   - **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - **Windows (CMD)**:
     ```cmd
     .venv\Scripts\activate.bat
     ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the tests**:
   ```bash
   pytest -v
   ```

## Test Architecture

### Services Under Test

The E2E test suite deploys the following services via Docker Compose:

1. **Broadcast Channel (PostgreSQL)**: Pub/sub backend for OPAL Server
   - Port: 5432 (internal)
   - Database: postgres
   
2. **OPAL Server**: Policy and data distribution server
   - Port: 7002
   - Connected to: broadcast_channel
   - Policy Repo: https://github.com/permitio/opal-example-policy-repo
   
3. **OPAL Client**: Policy agent management client
   - Port: 7000 (Client API)
   - Port: 8181 (OPA API)
   - Connected to: opal_server

### Test Suite Structure

```
e2e-tests/
├── conftest.py           # PyTest fixtures and setup
├── test_e2e.py           # Main E2E test cases
├── docker-compose.yml    # Docker Compose configuration
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## Test Cases

### 1. Health Checks
- **`test_opal_server_health`**: Verifies OPAL Server health endpoint returns HTTP 200
- **`test_opal_client_health`**: Verifies OPAL Client health endpoint returns HTTP 200
- **`test_opa_health`**: Verifies OPA health endpoint returns HTTP 200

### 2. Integration Tests
- **`test_opal_client_server_connection`**: 
  - Confirms OPAL Client connects to Server
  - Validates client receives policy updates
  - Checks statistics API for connection status
  - Times out after 30 seconds if connection fails

### 3. Log Validation
- **`test_no_critical_logs`**:
  - Scans service logs for ERROR messages
  - Scans service logs for CRITICAL messages
  - Fails if any critical issues are detected

## Available Fixtures

The following PyTest fixtures are available (defined in `conftest.py`):

- **`docker_compose_file`**: Path to docker-compose.yml
- **`docker_compose_project_name`**: Isolated project name for test runs
- **`opal_server_url`**: OPAL Server URL (waits for service to be ready)
- **`opal_client_url`**: OPAL Client URL (waits for service to be ready)
- **`opa_url`**: OPA API URL (waits for service to be ready)
- **`docker_compose_logs`**: Captured logs from all services after tests

## Running Specific Tests

### Run a Single Test
```bash
pytest test_e2e.py::test_opal_server_health -v
```

### Run Tests with Coverage
```bash
pytest --cov=../packages/opal-client --cov=../packages/opal-server --cov-report=term-missing
```

### Run Tests with Detailed Output
```bash
pytest -vv --tb=long
```

### Run Tests and Keep Containers Running (Debug)
```bash
pytest --keep-containers -v
```

## Troubleshooting

### Tests Fail with Connection Errors

**Problem**: Tests fail with `ConnectionError` or timeout errors.

**Solutions**:
1. Ensure Docker is running
2. Check if ports 7002, 7000, or 8181 are already in use:
   ```bash
   # Linux/Mac
   lsof -i :7002
   lsof -i :7000
   lsof -i :8181
   
   # Windows
   netstat -ano | findstr :7002
   netstat -ano | findstr :7000
   netstat -ano | findstr :8181
   ```
3. Clean up any existing containers:
   ```bash
   docker-compose -f docker-compose.yml down
   ```

### Tests Fail Due to Missing Images

**Problem**: Docker cannot pull OPAL images.

**Solutions**:
1. Pull images manually:
   ```bash
   docker pull permitio/opal-server:latest
   docker pull permitio/opal-client:latest
   docker pull postgres:alpine
   ```
2. Build images locally (from project root):
   ```bash
   make docker-build-server
   make docker-build-client
   ```

### Virtual Environment Issues

**Problem**: Dependencies are not installed correctly.

**Solutions**:
1. Delete and recreate the virtual environment:
   ```bash
   rm -rf .venv
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

### Port Already in Use

**Problem**: `Cannot bind to port` error.

**Solutions**:
1. Find and kill processes using the ports:
   ```bash
   # Linux/Mac
   kill $(lsof -t -i:7002)
   
   # Windows (PowerShell)
   Get-Process -Id (Get-NetTCPConnection -LocalPort 7002).OwningProcess | Stop-Process
   ```
2. Or use different ports by modifying `docker-compose.yml`

## Adding New Tests

To add new E2E tests:

1. **Add test function** to `test_e2e.py`:
   ```python
   def test_my_new_feature(opal_client_url):
       """Test description."""
       response = requests.get(f"{opal_client_url}/my-endpoint")
       assert response.status_code == 200
   ```

2. **Use existing fixtures** for URLs and services:
   - `opal_server_url`: OPAL Server base URL
   - `opal_client_url`: OPAL Client base URL
   - `opa_url`: OPA base URL

3. **Run your new test**:
   ```bash
   pytest test_e2e.py::test_my_new_feature -v
   ```

## Configuration

### Environment Variables

You can customize the test environment by modifying `docker-compose.yml`:

```yaml
services:
  opal_server:
    environment:
      - OPAL_BROADCAST_URI=postgres://postgres:postgres@broadcast_channel:5432/postgres
      - OPAL_POLICY_REPO_URL=https://github.com/permitio/opal-example-policy-repo
      - OPAL_POLICY_REPO_POLLING_INTERVAL=5  # Poll every 5 seconds
      - OPAL_LOG_FORMAT_INCLUDE_PID=true     # Include PID in logs
```

### Test Timeouts

Adjust timeouts in `conftest.py` if services take longer to start:

```python
docker_services.wait_until_responsive(
    timeout=90.0,  # Increase if needed
    pause=0.1,
    check=lambda: check_health(f"{url}/health")
)
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Run E2E Tests
        run: make test-e2e
```

## Related Documentation

- [OPAL Documentation](https://docs.opal.ac)
- [PyTest Documentation](https://docs.pytest.org)
- [PyTest-Docker Plugin](https://github.com/avast/pytest-docker)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

## Issue #677 Status

This E2E test framework implements the requirements from [Issue #677](https://github.com/permitio/opal/issues/677):

- ✅ Run OPAL Server and Client inside Docker
- ✅ Test for health check responsivity
- ✅ Check logs for errors and critical alerts
- ✅ Check client and server are connected using Statistics API
- ✅ Single test command to run all assertions

### Statistics API Testing

The framework now includes comprehensive Statistics API testing:

- **`test_statistics_endpoint_accessible`**: Verifies the statistics endpoint is accessible on the server
- **`test_client_server_connection_via_statistics`**: Core test that verifies client-server connection using the Statistics API (as required by issue #677)

Statistics are enabled by default in the test configuration (`OPAL_STATISTICS_ENABLED=true`). The tests verify that:
1. The statistics endpoint is accessible
2. Clients are properly registered in the server statistics
3. The connection between client and server is active and functional

## Contributing

To improve these tests:

1. Add more test cases to cover edge cases
2. Improve error messages for better debugging
3. Add performance benchmarks
4. Test more OPAL features (data updates, policy changes, etc.)

See [CONTRIBUTING.md](../CONTRIBUTING.md) for general contribution guidelines.
