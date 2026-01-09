# OPAL E2E Test Framework

This is a pytest based end to end testing framework for OPAL Server and Client.

## What This Does

Tests OPAL running in Docker just like it would in production. Spins up:
- OPAL Server (with statistics turned on)
- OPAL Client (with OPA embedded)
- PostgreSQL for the broadcast channel
- Health check validation
- Log checking for errors
- Statistics API verification

## How to Run

### What You Need First

1. Docker and Docker Compose need to be installed
2. Install the Python test dependencies:

```bash
pip install -r tests/requirements-e2e.txt
```

### Running the Tests

Just one command runs everything:

```bash
make e2e-test
```

Or if you want to use pytest directly:

```bash
cd tests/e2e && pytest -v
```

### Other Useful Commands

```bash
# Get more detailed output when debugging
make e2e-test-verbose

# Clean up all the Docker stuff
make e2e-test-clean

# Nuke everything and run fresh
make e2e-test-reset
```

## What Gets Tested

### Health Checks (test_health_checks.py)
- Server /healthcheck endpoint works
- Client /healthcheck endpoint works
- Client /healthy endpoint shows if its online
- Client /ready endpoint for readiness probes

### Statistics API (test_statistics.py)
- Server statistics are enabled and working
- Client shows up in server statistics
- Both /stats and /statistics endpoints match up

### Connectivity (test_connectivity.py)
- Client actually connects to the server (checks logs)
- Client gets the initial policy bundle
- Server logs show the client connected
- Statistics API confirms the connection
- OPA is running and has policies loaded

### Log Validation (test_logs.py)
- No ERROR logs in the server
- No CRITICAL logs in the server
- No ERROR logs in the client
- No CRITICAL logs in the client
- No exception tracebacks anywhere
- All the expected startup messages are there

## File Structure

```
tests/e2e/
├── conftest.py              # pytest fixtures for Docker, HTTP clients, logs
├── docker_compose.yml       # Docker setup for the test environment
├── test_health_checks.py    # Tests for health endpoints
├── test_statistics.py       # Tests for stats API
├── test_connectivity.py     # Tests for client server connection
├── test_logs.py             # Tests that check for errors in logs
└── utils/
    ├── docker_manager.py    # Handles Docker Compose lifecycle
    ├── http_client.py       # HTTP client with retries built in
    ├── log_parser.py        # Searches and filters logs
    └── wait_utils.py        # Helper for waiting with timeouts
```

## Pytest Fixtures Available

### Session Level (starts once and reused)

- `docker_manager`: handles the Docker Compose lifecycle
- `docker_services`: starts everything and waits for health checks to pass

### Test Level (fresh for each test)

- `server_client`: HTTP client pointing at OPAL Server on port 17002
- `client_client`: HTTP client pointing at OPAL Client on port 17000
- `opa_client`: HTTP client pointing at OPA on port 18181
- `server_logs`: parses server logs
- `client_logs`: parses client logs
- `wait_for_condition`: helps you wait for async stuff with retries

## Configuration

### Picking Which Docker Images to Test

You can control which OPAL images get tested:

```bash
OPAL_IMAGE_TAG=latest make e2e-test
OPAL_IMAGE_TAG=next make e2e-test
```

### Port Numbers

These tests use different ports so they don't conflict with any OPAL instances you might already have running:
- 17002 for OPAL Server (normally 7002)
- 17000 for OPAL Client (normally 7000)
- 18181 for OPA (normally 8181)

## Writing Your Own Tests

### Basic Test Example

```python
import pytest

@pytest.mark.e2e
class TestMyFeature:
    def test_something(self, server_client, client_client):
        response = server_client.get("/my-endpoint")
        assert response.status_code == 200
```

### Using the Fixtures

```python
def test_with_logs(self, server_logs, client_logs):
    # Look for something in the logs
    assert server_logs.has_pattern("expected message")

    # Check for errors
    errors = client_logs.filter_by_level("ERROR")
    assert len(errors) == 0

def test_with_retry(self, server_client, wait_for_condition):
    def check_condition():
        response = server_client.get("/endpoint")
        return response.status_code == 200

    # Keep trying for up to 30 seconds
    wait_for_condition(check_condition, timeout=30, interval=2)
```

## Troubleshooting

### Tests Won't Start

```bash
# Make sure Docker is actually running
docker ps

# Clean up any leftover containers from before
make e2e-test-clean

# Run again with more output to see what's wrong
make e2e-test-verbose
```

### Services Stay Unhealthy

```bash
# Check what's going on in the logs
docker compose -f tests/e2e/docker_compose.yml -p opal-e2e-tests logs opal_server
docker compose -f tests/e2e/docker_compose.yml -p opal-e2e-tests logs opal_client
```

### Port Already In Use

If you get port conflicts, just edit docker_compose.yml and change the ports:

```yaml
ports:
  - "27002:7002"  # pick a different port
```

### Tests Take Forever

Yeah they take 1 to 3 minutes to run because they need to:
1. Pull the Docker images (only on first run though)
2. Start up the containers and wait for them to be healthy
3. Wait for the client to connect and get policies

The good news is the containers only start once per test run, so it's not as slow as it could be.

## Running in CI/CD

If you want to add this to your CI pipeline:

```yaml
- name: Install E2E test dependencies
  run: pip install -r tests/requirements-e2e.txt

- name: Run E2E tests
  run: make e2e-test
```

## What This Covers

- Single command to run everything
- Real Docker containers for Server and Client
- All health check endpoints get tested
- Logs are checked for errors and critical issues
- Client and server connection verified through Statistics API
- Clean pass/fail output that's easy to read
