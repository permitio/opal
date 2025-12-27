# E2E Testing Framework - Verification Checklist

Use this checklist to verify that the E2E testing framework is working correctly.

## ✅ Pre-flight Checks

### Prerequisites
- [ ] Python 3.9+ is installed
  ```bash
  python --version  # Should show 3.9 or higher
  ```
- [ ] Docker is installed and running
  ```bash
  docker --version
  docker ps  # Should not error
  ```
- [ ] Docker Compose is installed
  ```bash
  docker compose version  # or: docker-compose --version
  ```
- [ ] Git repository is cloned
  ```bash
  git status  # Should show you're in the opal repository
  ```

## 📁 File Structure Verification

### Check that all files exist:
- [ ] `e2e-tests/conftest.py` exists
- [ ] `e2e-tests/test_e2e.py` exists
- [ ] `e2e-tests/docker-compose.yml` exists
- [ ] `e2e-tests/requirements.txt` exists
- [ ] `e2e-tests/README.md` exists (NEW)
- [ ] `e2e-tests/IMPLEMENTATION_STATUS.md` exists (NEW)
- [ ] `Makefile` contains `test-e2e` target
- [ ] Main `README.md` has "Testing OPAL" section

### Quick verification command:
```bash
ls -la e2e-tests/
# Should show: conftest.py, test_e2e.py, docker-compose.yml, requirements.txt, README.md, IMPLEMENTATION_STATUS.md
```

## 🧪 Test Execution Verification

### Method 1: Using Make (Recommended)
```bash
cd /path/to/opal  # Navigate to project root
make test-e2e
```

**Expected behavior:**
- [ ] Virtual environment is created (if not exists)
- [ ] Dependencies are installed
- [ ] Docker containers start
- [ ] All 5 tests pass:
  - [ ] test_opal_server_health
  - [ ] test_opal_client_health
  - [ ] test_opa_health
  - [ ] test_opal_client_server_connection
  - [ ] test_no_critical_logs
- [ ] Containers are cleaned up
- [ ] Exit code is 0

### Method 2: Manual Execution
```bash
cd e2e-tests
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -v
```

**Expected behavior:**
- [ ] Virtual environment is created successfully
- [ ] All dependencies install without errors
- [ ] PyTest discovers 5 tests
- [ ] All 5 tests pass
- [ ] No errors in output

## 🔍 Individual Test Verification

### Test 1: OPAL Server Health
```bash
pytest test_e2e.py::test_opal_server_health -v
```
- [ ] Test passes
- [ ] Output shows "PASSED"

### Test 2: OPAL Client Health
```bash
pytest test_e2e.py::test_opal_client_health -v
```
- [ ] Test passes
- [ ] Output shows "PASSED"

### Test 3: OPA Health
```bash
pytest test_e2e.py::test_opa_health -v
```
- [ ] Test passes
- [ ] Output shows "PASSED"

### Test 4: Client-Server Connection
```bash
pytest test_e2e.py::test_opal_client_server_connection -v
```
- [ ] Test passes
- [ ] Output shows "PASSED"
- [ ] Takes ~5-30 seconds to complete

### Test 5: Log Validation
```bash
pytest test_e2e.py::test_no_critical_logs -v
```
- [ ] Test passes
- [ ] Output shows "PASSED"

## 🐳 Docker Verification

### Check running containers during tests
```bash
# In another terminal while tests are running
docker ps
```

**Should show:**
- [ ] `opal_e2e_tests_broadcast_channel_*` (PostgreSQL)
- [ ] `opal_e2e_tests_opal_server_*` (OPAL Server)
- [ ] `opal_e2e_tests_opal_client_*` (OPAL Client)

### Check containers are cleaned up after tests
```bash
docker ps -a | grep opal_e2e_tests
```
- [ ] No containers remain (or only stopped ones if using --keep-containers)

### Verify images are available
```bash
docker images | grep opal
```
- [ ] `permitio/opal-server` exists
- [ ] `permitio/opal-client` exists

## 📊 Coverage Verification (Optional)

```bash
pytest --cov=../packages/opal-client --cov=../packages/opal-server --cov-report=term-missing
```

- [ ] Coverage report is generated
- [ ] No errors in coverage collection
- [ ] Coverage percentage is shown

## 📖 Documentation Verification

### Check README.md files
- [ ] `e2e-tests/README.md` is readable and well-formatted
- [ ] Main `README.md` has testing section
- [ ] Links in documentation work

### Verify documentation accuracy
- [ ] Commands in README actually work
- [ ] Examples are correct
- [ ] Prerequisites are listed
- [ ] Troubleshooting section is helpful

## 🔧 Troubleshooting Verification

### Test common issues from documentation:

1. **Port conflicts**
   ```bash
   # Should list which ports are in use
   netstat -an | grep -E "7002|7000|8181"
   ```
   - [ ] No conflicts detected

2. **Docker cleanup**
   ```bash
   docker-compose -f docker-compose.yml down
   docker system prune -f
   ```
   - [ ] Cleanup works without errors

3. **Virtual environment recreation**
   ```bash
   rm -rf .venv
   python -m venv .venv
   ```
   - [ ] Can recreate venv successfully

## 🎯 Issue #677 Requirements Verification

### Requirement 1: Docker Setup
- [ ] OPAL Server runs in Docker
- [ ] OPAL Client runs in Docker
- [ ] Services communicate correctly

### Requirement 2: Health Checks
- [ ] Server health check works
- [ ] Client health check works
- [ ] OPA health check works

### Requirement 3: Log Validation
- [ ] Logs are captured
- [ ] Errors are detected
- [ ] Critical alerts are caught

### Requirement 4: Connection Test
- [ ] Statistics API is accessible
- [ ] Connection status is verified
- [ ] Policy updates are confirmed

### Requirement 5: Single Command
- [ ] `make test-e2e` works from root
- [ ] All setup is automated
- [ ] Clean exit on success

## 🚦 Final Verification

### Overall Test Status
Run all tests one final time:
```bash
make test-e2e
```

**Final checklist:**
- [ ] All 5 tests pass ✅
- [ ] No errors in output
- [ ] Execution time < 2 minutes
- [ ] Clean exit (return code 0)
- [ ] No containers left running
- [ ] Documentation is complete
- [ ] Ready for production use

## 📝 Sign-off

Once all items are checked, the E2E testing framework is:
- ✅ Fully implemented
- ✅ Properly documented
- ✅ Working correctly
- ✅ Ready for Issue #677 closure

---

## 🆘 If Anything Fails

1. **Check Docker**: `docker info` should work
2. **Check Python**: `python --version` should be 3.9+
3. **Check ports**: Kill any processes using 7002, 7000, or 8181
4. **Check logs**: Look at Docker container logs for specific errors
5. **Clean state**: Run `docker-compose down` and try again
6. **Review documentation**: See `e2e-tests/README.md` troubleshooting section

---

## ✅ Verification Complete!

If all checkboxes are marked, the E2E testing framework is working perfectly and Issue #677 can be closed! 🎉
