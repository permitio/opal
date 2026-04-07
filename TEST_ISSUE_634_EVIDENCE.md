# Test Evidence for Issue #634 Fix

## Issue Description
When OPAL server has GitHub policies setup and GitHub is down for some time, OPAL server seems to spawn zombie processes but apparently looks like it is just a list of symbolic links that are not cleaned up in `/proc`.

## Fix Summary
The fix adds proper cleanup of Repository objects from cache when Git operations fail, preventing file descriptors from being held open and leaving symbolic links in `/proc`.

## Code Changes

### 1. Added `_cleanup_repo_from_cache()` Method
**Location**: `packages/opal-server/opal_server/git_fetcher.py`

This method explicitly removes Repository objects from the cache, allowing Python's garbage collector to clean up file descriptors:

```python
def _cleanup_repo_from_cache(self):
    """Remove repository from cache to ensure proper cleanup of file descriptors.
    
    This is important when GitHub is down and operations fail, as pygit2
    Repository objects may hold file descriptors that can leave symbolic
    links in /proc if not properly cleaned up.
    """
    path = str(self._repo_path)
    if path in GitPolicyFetcher.repos:
        try:
            # Explicitly remove from cache to allow garbage collection
            # This helps prevent file descriptors from being held open
            del GitPolicyFetcher.repos[path]
            logger.debug(f"Removed invalid repo from cache: {path}")
        except KeyError:
            pass  # Already removed
```

### 2. Enhanced Fetch Error Handling
**Location**: `packages/opal-server/opal_server/git_fetcher.py` - `fetch_and_notify_on_changes()`

When fetch operations fail (e.g., GitHub returns 500), the Repository is now cleaned up from cache:

```python
try:
    await run_sync(
        repo.remotes[self._remote].fetch,
        callbacks=self._auth_callbacks,
    )
    logger.debug(f"Fetch completed: {self._source.url}")
except pygit2.GitError as e:
    # When GitHub is down or returns errors, pygit2 may leave
    # file descriptors open. Clean up the repo from cache to
    # prevent symbolic links from accumulating in /proc.
    logger.warning(
        f"Fetch failed for {self._source.url}: {e}. "
        "Cleaning up repository from cache to prevent file descriptor leaks."
    )
    self._cleanup_repo_from_cache()
    # Re-raise to allow retry logic to handle it
    raise
```

### 3. Enhanced Clone Error Handling
**Location**: `packages/opal-server/opal_server/git_fetcher.py` - `_clone()`

When clone operations fail, both the Repository cache and partial repository directories are cleaned up:

```python
except pygit2.GitError as e:
    logger.exception(f"Could not clone repo at {self._source.url}")
    # When GitHub is down or returns errors, pygit2 may leave file descriptors
    # or partially created repository directories. Clean up to prevent
    # symbolic links from accumulating in /proc.
    self._cleanup_repo_from_cache()
    # Clean up any partially created repository directory
    if self._repo_path.exists():
        try:
            logger.warning(
                f"Cleaning up partially created repository at {self._repo_path}"
            )
            shutil.rmtree(self._repo_path)
        except Exception as cleanup_error:
            logger.warning(
                f"Failed to clean up partial repository at {self._repo_path}: {cleanup_error}"
            )
    # Re-raise to allow retry logic to handle it
    raise
```

### 4. Cleanup Before Directory Deletion
**Location**: `packages/opal-server/opal_server/git_fetcher.py` - `fetch_and_notify_on_changes()`

Repository is removed from cache before deleting invalid repository directories:

```python
else:
    # repo dir exists but invalid -> we must delete the directory
    logger.warning(
        "Deleting invalid repo: {path}", path=self._repo_path
    )
    # Clean up from cache before deleting directory
    self._cleanup_repo_from_cache()
    shutil.rmtree(self._repo_path)
```

## Test Files Created

### 1. Unit Tests
**File**: `packages/opal-server/opal_server/tests/test_git_fetcher_cleanup.py`

Comprehensive unit tests covering:
- ✅ Repository cleanup on fetch failure
- ✅ Repository cleanup on clone failure
- ✅ Partial repository directory cleanup
- ✅ Cache cleanup before directory deletion
- ✅ Multiple failure scenarios (no accumulation)
- ✅ Idempotent cleanup operations

### 2. Manual Test Script
**File**: `test_issue_634_manual.py`

Manual test script that simulates:
- GitHub being down (500 errors)
- Multiple fetch failures
- Clone failures
- Verification of cache cleanup
- Symlink count monitoring (on Linux)

## Test Execution Instructions

### Prerequisites
```bash
# Install dependencies
pip install pytest pytest-asyncio pygit2

# Or use the project's requirements
pip install -r packages/opal-server/requires.txt
pip install pytest pytest-asyncio
```

### Run Unit Tests
```bash
cd packages/opal-server
python -m pytest opal_server/tests/test_git_fetcher_cleanup.py -v
```

### Run Manual Tests
```bash
# From project root
python test_issue_634_manual.py
```

## Expected Test Results

### Unit Tests
All 6 unit tests should pass:
1. ✅ `test_cleanup_repo_from_cache_on_fetch_failure` - Repository removed from cache after fetch failure
2. ✅ `test_cleanup_repo_from_cache_on_clone_failure` - Repository and partial directory cleaned up after clone failure
3. ✅ `test_cleanup_repo_from_cache_on_invalid_repo` - Invalid repository removed from cache
4. ✅ `test_cleanup_repo_from_cache_method` - Cleanup method works correctly
5. ✅ `test_cleanup_before_deleting_invalid_repo_directory` - Cache cleaned before directory deletion
6. ✅ `test_multiple_cleanup_calls_safe` - Multiple cleanup calls are safe

### Manual Tests
All 3 manual tests should pass:
1. ✅ Fetch Failure Cleanup - Repository removed from cache, symlink count stable
2. ✅ Clone Failure Cleanup - Partial directory cleaned up, cache cleaned
3. ✅ Multiple Failures - No accumulation of Repository objects in cache

## Verification Checklist

- [x] Code changes implemented
- [x] Unit tests created
- [x] Manual test script created
- [ ] Unit tests executed and passed
- [ ] Manual tests executed and passed
- [ ] Cache cleanup verified
- [ ] File descriptor cleanup verified
- [ ] No symbolic link accumulation verified

## How to Verify the Fix in Production

1. **Monitor Repository Cache Size**:
   ```python
   # Check cache size before and after failures
   len(GitPolicyFetcher.repos)
   ```

2. **Monitor /proc Symlinks** (Linux only):
   ```bash
   # Count symlinks in /proc
   ls -la /proc | grep "^l" | wc -l
   ```

3. **Check Logs for Cleanup Messages**:
   Look for log messages like:
   - "Cleaning up repository from cache to prevent file descriptor leaks"
   - "Cleaning up partially created repository at ..."
   - "Removed invalid repo from cache: ..."

4. **Simulate GitHub Downtime**:
   - Block GitHub access (firewall, DNS, etc.)
   - Trigger policy fetches
   - Verify cache doesn't grow
   - Verify no new symlinks in /proc

## Code Review Points

1. **Cache Management**: Repository objects are explicitly removed from cache, allowing garbage collection
2. **Error Handling**: All Git operation failures trigger cleanup
3. **Resource Cleanup**: Both cache entries and file system artifacts are cleaned up
4. **Idempotency**: Cleanup operations are safe to call multiple times
5. **Logging**: Comprehensive logging for debugging and monitoring

## Related Files

- `packages/opal-server/opal_server/git_fetcher.py` - Main implementation
- `packages/opal-server/opal_server/tests/test_git_fetcher_cleanup.py` - Unit tests
- `test_issue_634_manual.py` - Manual test script

## Commit Information

**Branch**: `fix/issue-634-symlink-cleanup`
**Commit**: `f13f0ca` - "Fix issue #634: Clean up symbolic links in /proc when GitHub is down"
