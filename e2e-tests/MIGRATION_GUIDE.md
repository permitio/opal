# Migration Guide: Old to New E2E Tests

This guide helps teams migrate from the original E2E tests to the improved version.

## Quick Summary

The new test suite maintains **100% backward compatibility** while adding significant improvements. Existing workflows continue to work unchanged.

## What Stays the Same ✅

1. **Command to run tests**: `make test-e2e` still works
2. **Docker setup**: Same docker-compose.yml configuration
3. **Core fixtures**: `opal_server_url`, `opal_client_url`, `opa_url` unchanged
4. **Basic assertions**: All original test validations maintained

## What's New 🎉

### 1. More Tests (5 → 21 tests)

**Old:**
```python
def test_opal_server_health(opal_server_url):
    response = requests.get(f"{opal_server_url}/health")
    assert response.status_code == 200
```

**New:**
```python
class TestHealthChecks:
    def test_opal_server_health(self, opal_server_url):
        """Test with better error messages and validation."""
        response = requests.get(f"{opal_server_url}/health", timeout=10)
        
        assert response.status_code == 200, \
            f"Server health check failed with status {response.status_code}"
        
        data = response.json()
        assert data == {"status": "ok"}, \
            f"Server health check returned unexpected data: {data}"
```

**What changed:**
- ✅ Tests organized into classes
- ✅ Better docstrings
- ✅ Improved error messages
- ✅ Added timeout handling
- ✅ More assertions

### 2. New Dependencies

**Old requirements.txt:**
```
pytest
requests
pytest-docker
pytest-cov
```

**New requirements.txt:**
```
# Same as before, plus:
pytest-timeout>=2.1.0
pytest-xdist>=3.0.0
pytest-html>=3.1.0
pytest-json-report>=1.5.0
pytest-benchmark>=4.0.0
pytest-clarity>=1.0.0
faker>=18.0.0
colorlog>=6.7.0
```

**Migration:**
```bash
cd e2e-tests
pip install -r requirements.txt --upgrade
```

### 3. New Utilities

**New helper functions available:**

```python
# Wait for any condition
def test_my_feature(self, wait_for):
    success = wait_for(
        lambda: check_something(),
        timeout=30,
        description="Something to happen"
    )

# HTTP requests with retries
def test_api_call(self, make_request):
    response = make_request("http://example.com", max_retries=3)
```

### 4. New Configuration File

**New: pytest.ini**
- Configures test discovery
- Sets logging levels
- Defines markers
- Configures coverage

**No action needed** - works automatically

## Migration Steps

### Option 1: Gradual Migration (Recommended)

Keep both test files temporarily:

```bash
# Rename old tests
mv test_e2e.py test_e2e_old.py

# Copy new tests
# (new test_e2e.py already in place)

# Run both
pytest test_e2e_old.py -v  # Old tests
pytest test_e2e.py -v      # New tests

# When confident, remove old
rm test_e2e_old.py
```

### Option 2: Direct Replacement

```bash
# Backup old tests
cp test_e2e.py test_e2e_backup.py

# New test file is already in place
# Install new dependencies
pip install -r requirements.txt --upgrade

# Run tests
pytest -v

# If everything works, remove backup
rm test_e2e_backup.py
```

## Compatibility Matrix

| Feature | Old Tests | New Tests | Compatible? |
|---------|-----------|-----------|-------------|
| `make test-e2e` | ✅ | ✅ | ✅ Yes |
| `pytest -v` | ✅ | ✅ | ✅ Yes |
| Basic fixtures | ✅ | ✅ | ✅ Yes |
| Docker setup | ✅ | ✅ | ✅ Yes |
| Log validation | ✅ | ✅ | ✅ Yes |
| CI/CD integration | ✅ | ✅ | ✅ Yes |

## Breaking Changes

**None!** The new test suite is 100% backward compatible.

## New Features You Get

### 1. Test Organization

**Before:**
```
test_e2e.py
  - test_opal_server_health
  - test_opal_client_health
  - test_opa_health
  - test_opal_client_server_connection
  - test_no_critical_logs
```

**After:**
```
test_e2e.py
  TestHealthChecks
    - test_opal_server_health
    - test_opal_client_health
    - test_opa_health
    - test_all_services_respond_quickly
  TestConnectivity
    - test_opal_client_server_connection
    - test_statistics_endpoint_structure
    - test_server_broadcast_channel_connection
  TestPolicyOperations
    - test_opa_policies_loaded
    - test_opa_data_endpoint_accessible
    - test_policy_query_execution
  ... and more
```

### 2. Better Commands

```bash
# Run only health checks
pytest test_e2e.py::TestHealthChecks -v

# Run performance tests
pytest -m benchmark -v

# Parallel execution
pytest -n auto

# Generate HTML report
pytest --html=report.html
```

### 3. Better Error Messages

**Old:**
```
AssertionError: assert 'ERROR' not in 'LOGS WITH ERROR MESSAGE...'
```

**New:**
```
AssertionError: Critical errors found in logs:
opal_server: ['2024-01-15 10:30:00 [ERROR] Connection failed']
opal_client: ['2024-01-15 10:30:01 [ERROR] Policy sync failed']
```

### 4. Performance Benchmarks

```bash
# Run benchmarks
pytest -m benchmark -v

# Output:
Test: test_health_check_response_time
OPAL Server: 45.23ms
OPAL Client: 52.18ms
OPA: 38.91ms
```

## CI/CD Integration

### No Changes Needed

Existing CI/CD pipelines continue to work:

```yaml
# Still works!
- name: Run E2E Tests
  run: make test-e2e
```

### Optional Improvements

```yaml
# Enhanced with new features
- name: Run E2E Tests
  run: |
    cd e2e-tests
    pytest --junitxml=junit.xml \
           --cov=. \
           --cov-report=xml \
           --html=report.html \
           -n auto
```

## Troubleshooting

### Issue: New dependencies won't install

**Solution:**
```bash
# Upgrade pip first
pip install --upgrade pip

# Then install requirements
pip install -r requirements.txt
```

### Issue: Tests take longer now

**Cause:** More tests = more time (but can be parallelized)

**Solution:**
```bash
# Run tests in parallel
pytest -n auto  # Uses all CPU cores
```

### Issue: Some new tests fail

**Cause:** Stricter validation or timing issues

**Solutions:**
1. Check if services have enough resources
2. Increase timeouts in docker-compose.yml
3. Run with `-vv` for detailed output
4. Check logs: `pytest -v --log-cli-level=DEBUG`

### Issue: Want to skip new tests temporarily

**Solution:**
```bash
# Run only original 5 tests
pytest test_e2e.py::TestHealthChecks::test_opal_server_health \
       test_e2e.py::TestHealthChecks::test_opal_client_health \
       test_e2e.py::TestHealthChecks::test_opa_health \
       test_e2e.py::TestConnectivity::test_opal_client_server_connection \
       test_e2e.py::TestSystemReliability::test_no_critical_logs

# Or skip slow tests
pytest -m "not slow" -v
```

## Gradual Adoption Strategy

### Phase 1: Validation (Week 1)
```bash
# Run both old and new tests side by side
pytest test_e2e_old.py -v
pytest test_e2e.py -v
```

### Phase 2: Integration (Week 2)
```bash
# Start using new tests in dev
# Keep old tests in CI/CD
```

### Phase 3: Full Migration (Week 3+)
```bash
# Switch CI/CD to new tests
# Remove old test file
```

## Getting Help

### Documentation
- 📖 **README.md** - Quick start
- 📚 **ADVANCED_TESTING_GUIDE.md** - Comprehensive guide
- ✅ **VERIFICATION_CHECKLIST.md** - Test checklist
- 📊 **IMPLEMENTATION_STATUS.md** - Feature status

### Support Channels
- 🐛 GitHub Issues
- 💬 OPAL Slack Community
- 📧 Team discussion

## FAQ

**Q: Do I need to change my Makefile?**  
A: No, `make test-e2e` still works the same way.

**Q: Will my CI/CD pipeline break?**  
A: No, all existing commands remain compatible.

**Q: Do I need to learn new fixtures?**  
A: No, all original fixtures work. New fixtures are optional additions.

**Q: Can I keep using the old test file?**  
A: Yes, but you'll miss out on improvements. The new tests are backward compatible.

**Q: How long does migration take?**  
A: 15 minutes for Option 2 (direct replacement), 1-3 weeks for Option 1 (gradual).

**Q: What if I find a bug?**  
A: Open a GitHub issue or revert to the old tests temporarily.

## Checklist

Migration is complete when:

- [ ] New requirements.txt installed
- [ ] New test file in place
- [ ] `pytest -v` runs successfully
- [ ] `make test-e2e` runs successfully
- [ ] All 21 tests pass
- [ ] CI/CD pipeline tested
- [ ] Team is familiar with new features
- [ ] Old test file removed (optional)
- [ ] Documentation reviewed

## Summary

✅ **100% backward compatible**  
✅ **No breaking changes**  
✅ **All existing commands work**  
✅ **Gradual migration possible**  
✅ **Significant improvements added**  

**Migration is safe and straightforward!** 🚀

---

**Questions?** Check the [ADVANCED_TESTING_GUIDE.md](ADVANCED_TESTING_GUIDE.md) or ask in Slack!
