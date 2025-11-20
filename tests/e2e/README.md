# OPAL E2E Tests

This directory contains End-to-End (E2E) tests for OPAL using PyTest framework.

## Overview

The E2E tests verify that OPAL Server and OPAL Client work correctly together by:
- Starting Docker services automatically
- Testing health endpoints
- Validating statistics API
- Checking logs for errors
- Verifying client-server connectivity

## Prerequisites

- Python 3.7+
- Docker and Docker Compose
- Required Python packages (install with `pip install -r requirements.txt`)

## Running Tests

### Quick Start
```bash
# Run all E2E tests
pytest tests/e2e -q

# Run with verbose output
pytest tests/e2e -v

# Run specific test file
pytest tests/e2e/test_health.py -v
```

### Using the Test Runner
```bash
# Alternative way to run tests
python run_e2e_tests.py
```

## Test Structure

- `conftest.py` - PyTest fixtures and Docker service management
- `test_health.py` - Health endpoint validation
- `test_stats.py` - Statistics API and connection tests
- `test_logs.py` - Log validation and error detection

## What Gets Tested

### Health Tests
- Server `/healthcheck` endpoint returns 200
- Server `/` root endpoint returns 200
- Response time is reasonable

### Statistics Tests
- Statistics endpoints are accessible
- JSON response structure is valid
- Client-server connection status

### Log Tests
- No ERROR or CRITICAL messages in logs
- Successful startup messages present
- Both services produce logs

## Configuration

Tests use the existing `docker/docker-compose-example.yml` configuration with:
- OPAL Server on port 7002
- OPAL Client on port 7766
- OPA on port 8181

## Troubleshooting

### Port Conflicts
If tests fail due to port conflicts, ensure ports 7002, 7766, and 8181 are available.

### Docker Issues
```bash
# Clean up Docker resources
docker-compose -f docker/docker-compose-example.yml down -v

# Check Docker status
docker ps
```

### Timeout Issues
If services take longer to start, increase `HEALTH_CHECK_TIMEOUT` in `conftest.py`.

## Adding New Tests

1. Create new test files following the `test_*.py` pattern
2. Use the `@pytest.mark.e2e` and `@pytest.mark.docker` markers
3. Utilize existing fixtures from `conftest.py`
4. Follow the existing code style and patterns


## To check it's working proeprly:
1. Terminal in docker folder:
cd /Users/kartikbhardwaj/Desktop/opal/opal/docker
docker compose -f docker-compose-with-statistics.yml ps
2. Health check working:
curl http://localhost:7002/healthcheck
curl http://localhost:7002/statistics
3. E2E tests passing:
cd /Users/kartikbhardwaj/Desktop/opal/opal
source venv/bin/activate
pytest tests/e2e -q
4. Show final result:
======================== 11 passed, 1 warning in 5.61s =========================
