# OPAL PyTest E2E Testing Framework

This directory contains a comprehensive PyTest-based end-to-end testing framework for OPAL, replacing the previous bash-based approach (`app-tests/run.sh`).

## Overview

The PyTest E2E framework provides:

- **Automated Environment Setup**: Automatically sets up Gitea, OPAL server, OPAL client, and all dependencies
- **Comprehensive Test Coverage**: Tests for health checks, connectivity, policy updates, data updates, statistics, and resilience
- **Better Maintainability**: Python-based tests are easier to read, write, and maintain than bash scripts
- **Modular Design**: Reusable fixtures and helper functions
- **Detailed Reporting**: PyTest's built-in reporting and assertion messages
- **Parallel Execution**: Can run tests in parallel with pytest-xdist (optional)

## Architecture

### Files

- **`conftest.py`**: PyTest configuration and fixtures
  - `opal_keys`: Generates authentication keys and tokens
  - `policy_repo`: Sets up Gitea and policy repository
  - `opal_environment`: Starts OPAL server and client containers
  - `compose_command`: Helper for running docker-compose commands

- **`test_opal_e2e.py`**: Main test suite
  - `TestOPALHealth`: Health endpoint tests
  - `TestOPALConnectivity`: Server-client connectivity tests
  - `TestOPALPolicyUpdates`: Policy update tests
  - `TestOPALDataUpdates`: Data update tests
  - `TestOPALStatistics`: Statistics endpoint tests
  - `TestOPALResilience`: Resilience and recovery tests

- **`__init__.py`**: Package initialization
- **`README.md`**: This file

## Prerequisites

- Docker and Docker Compose
- Python 3.8+
- PyTest and dependencies (see `requirements.txt`)

Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Tests

### Run all E2E tests:
```bash
pytest tests/e2e/
```

### Run with verbose output:
```bash
pytest tests/e2e/ -v
```

### Run with live output (see print statements):
```bash
pytest tests/e2e/ -s
```

### Run specific test class:
```bash
pytest tests/e2e/test_opal_e2e.py::TestOPALHealth
```

### Run specific test:
```bash
pytest tests/e2e/test_opal_e2e.py::TestOPALHealth::test_server_health
```

### Run with retries (for flaky tests):
```bash
pytest tests/e2e/ --reruns 3 --reruns-delay 5
```

### Run in parallel (requires pytest-xdist):
```bash
pytest tests/e2e/ -n auto
```

## Test Coverage

### 1. Health Tests (`TestOPALHealth`)
- ✅ OPAL server health endpoints
- ✅ OPAL client health endpoints

### 2. Connectivity Tests (`TestOPALConnectivity`)
- ✅ Client-server connection
- ✅ Policy bundle reception
- ✅ PubSub connection
- ✅ Static data loading
- ✅ No critical errors in logs

### 3. Policy Update Tests (`TestOPALPolicyUpdates`)
- ✅ Single policy push via git
- ✅ Multiple policy pushes
- ✅ Webhook triggering
- ✅ Client policy reception

### 4. Data Update Tests (`TestOPALDataUpdates`)
- ✅ Single data update via API
- ✅ Multiple data updates
- ✅ Client data reception

### 5. Statistics Tests (`TestOPALStatistics`)
- ✅ Statistics endpoint availability
- ✅ Correct client/server counts

### 6. Resilience Tests (`TestOPALResilience`)
- ✅ Broadcast channel restart recovery
- ✅ Data updates after recovery
- ✅ Policy updates after recovery

## Fixtures

### Session-scoped Fixtures

These fixtures are created once per test session and shared across all tests:

#### `opal_keys`
Generates OPAL authentication keys and tokens:
- SSH key pair (public/private)
- Master token
- Client token
- Datasource token

#### `policy_repo`
Sets up a local Gitea server and policy repository:
- Starts Gitea container
- Creates admin user
- Initializes policy repository
- Returns repository URLs and branch name

#### `opal_environment`
Sets up the complete OPAL environment:
- Creates `.env` file with authentication
- Starts OPAL server and client containers
- Waits for services to be ready
- Cleans up on teardown

### Function-scoped Fixtures

#### `compose_command`
Provides a helper function to run docker-compose commands with proper configuration.

## Environment Variables

The framework automatically manages these environment variables:

- `OPAL_AUTH_PUBLIC_KEY`: SSH public key for authentication
- `OPAL_AUTH_PRIVATE_KEY`: SSH private key for authentication
- `OPAL_AUTH_PRIVATE_KEY_PASSPHRASE`: Passphrase for private key
- `OPAL_AUTH_MASTER_TOKEN`: Master authentication token
- `OPAL_CLIENT_TOKEN`: Client authentication token
- `OPAL_POLICY_REPO_URL`: Git repository URL for policies
- `OPAL_POLICY_REPO_URL_FOR_WEBHOOK`: Internal Git repository URL
- `POLICY_REPO_BRANCH`: Git branch name for testing

## Comparison with Bash Script

### Advantages of PyTest Framework

1. **Better Error Handling**: Python exceptions vs bash error codes
2. **Easier Debugging**: PyTest's detailed assertion messages
3. **Modular Design**: Reusable fixtures and helper functions
4. **Type Safety**: Type hints for better IDE support
5. **Test Isolation**: Each test can be run independently
6. **Parallel Execution**: Can run tests in parallel
7. **Better Reporting**: HTML reports, JUnit XML, etc.
8. **Easier Maintenance**: Python is more readable than bash
9. **IDE Support**: Better autocomplete and refactoring tools
10. **Extensibility**: Easy to add new tests and fixtures

### Migration from Bash

The PyTest framework covers all functionality from `app-tests/run.sh`:

| Bash Function | PyTest Equivalent |
|---------------|-------------------|
| `generate_opal_keys` | `opal_keys` fixture |
| `prepare_policy_repo` | `policy_repo` fixture |
| `compose` | `compose_command` fixture |
| `check_clients_logged` | Assertions in test methods |
| `check_no_error` | `test_no_critical_errors_in_logs` |
| `test_push_policy` | `TestOPALPolicyUpdates` class |
| `test_data_publish` | `TestOPALDataUpdates` class |
| `test_statistics` | `TestOPALStatistics` class |
| `clean_up` | Fixture teardown |

## Troubleshooting

### Tests fail with timeout errors
- Increase timeout values in `conftest.py`
- Check Docker resource limits
- Ensure ports are not already in use

### Gitea fails to start
- Check port 3000 is available
- Verify Docker has enough resources
- Check Gitea logs: `docker logs gitea`

### OPAL services fail to start
- Check ports 7000-7003 are available
- Verify authentication keys were generated correctly
- Check OPAL logs: `docker compose -f app-tests/docker-compose-app-tests.yml logs`

### Policy/data updates not received
- Verify webhook URL is correct
- Check network connectivity between containers
- Increase sleep times in tests

### Clean up after failed tests
```bash
cd app-tests
docker compose -f docker-compose-app-tests.yml down -v
rm -rf opal-tests-policy-repo temp-repo gitea-data git-repos .env
```

## Contributing

When adding new tests:

1. Follow the existing test structure
2. Use descriptive test names
3. Add docstrings to test methods
4. Use appropriate fixtures
5. Add assertions with clear messages
6. Update this README with new test coverage

## Future Enhancements

Potential improvements:

- [ ] Add performance benchmarking tests
- [ ] Add security testing (authentication, authorization)
- [ ] Add multi-tenant testing
- [ ] Add Cedar policy engine tests
- [ ] Add custom policy store tests
- [ ] Add webhook security tests
- [ ] Add load testing
- [ ] Add chaos engineering tests
- [ ] Add integration with CI/CD metrics
- [ ] Add test coverage reporting

## License

Same as OPAL project license.
