# Refresh Scope Stale Commit Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the bug where OPAL Server, when handling a `POST /scopes/{scope_id}/refresh` request, sometimes publishes a "new commit" notification that is newer than the previously known commit but not the actual latest commit on the remote.

**Architecture:** The root cause is a Python staticmethod misuse in `git_fetcher.py`. The class-level `repos_last_fetched` dict — used by `_was_fetched_after` to deduplicate redundant fetches — is keyed by `self.source_id`, which is the unbound staticmethod function object (the same object across every instance), instead of the per-source hash string `GitPolicyFetcher.source_id(self._source)`. As a result, every source/scope shares one global "last fetched" timestamp, and a recent fetch on source X can cause a refresh request on unrelated source Y to be skipped. The fix is to compute and cache the source id once at construction time and use it consistently. A regression test verifies that two distinct sources do not collide in the cache.

**Tech Stack:** Python 3, pygit2, pytest, asyncio.

---

## Background — Root Cause Analysis

### Symptom
On `POST /scopes/{scope_id}/refresh` (with no `hinted_hash`, so `force_fetch=True`), OPAL Server publishes a policy update for a commit that is newer than the previous head but not the actual latest commit on the remote.

### Code path
1. [packages/opal-server/opal_server/scopes/api.py:179-220](../../packages/opal-server/opal_server/scopes/api.py#L179-L220) — refresh endpoint publishes `POLICY_REPO_WEBHOOK_TOPIC` with `{scope_id, force_fetch, hinted_hash}`.
2. [packages/opal-server/opal_server/scopes/task.py:50-63](../../packages/opal-server/opal_server/scopes/task.py#L50-L63) — `ScopesPolicyWatcherTask.trigger` stamps `req_time=datetime.now()` and calls `ScopesService.sync_scope`.
3. [packages/opal-server/opal_server/scopes/service.py:113-159](../../packages/opal-server/opal_server/scopes/service.py#L113-L159) — `sync_scope` constructs `GitPolicyFetcher` and calls `fetch_and_notify_on_changes(hinted_hash, force_fetch, req_time)`.
4. [packages/opal-server/opal_server/git_fetcher.py:156-212](../../packages/opal-server/opal_server/git_fetcher.py#L156-L212) — under the per-source lock, `_should_fetch` decides whether to fetch from remote, then `_notify_on_changes` reads the remote tracking ref and publishes a notification.

### The bug
[packages/opal-server/opal_server/git_fetcher.py:150-154](../../packages/opal-server/opal_server/git_fetcher.py#L150-L154) and [git_fetcher.py:190-192](../../packages/opal-server/opal_server/git_fetcher.py#L190-L192):

```python
async def _was_fetched_after(self, t: datetime.datetime):
    last_fetched = GitPolicyFetcher.repos_last_fetched.get(self.source_id, None)
    ...

GitPolicyFetcher.repos_last_fetched[
    self.source_id
] = datetime.datetime.now()
```

`source_id` is declared as a `@staticmethod` ([git_fetcher.py:352-359](../../packages/opal-server/opal_server/git_fetcher.py#L352-L359)) that takes a `source` argument and returns a hex-string key. Accessing `self.source_id` (no parentheses, no argument) returns the unbound staticmethod's underlying function object. In Python 3, `instance.staticmethod_name` returns the same function object across every instance, so `self.source_id` is identical for all sources/scopes. Used as a dict key, the entire `repos_last_fetched` dict therefore has at most **one entry**, shared by every source.

Compare with the correct usage on [git_fetcher.py:144](../../packages/opal-server/opal_server/git_fetcher.py#L144):
```python
src_id = GitPolicyFetcher.source_id(self._source)
```
That call site keys per-source correctly, so the per-source `repo_locks` work as intended — only `repos_last_fetched` is broken.

### Why this produces "sees a new commit but not the latest"
`_should_fetch` overrides `force_fetch=True` to False when `_was_fetched_after(req_time)` returns True ([git_fetcher.py:259-265](../../packages/opal-server/opal_server/git_fetcher.py#L259-L265)). With the shared key, *any* recent fetch on any other source can satisfy that check. Concrete repro:

1. Periodic poller (`POLICY_REFRESH_INTERVAL`) iterates scopes; for each scope it writes the shared key with `now()`.
2. New commit `C2` lands on source Y.
3. Refresh request for source Y arrives with no `hinted_hash` → `force_fetch=True`, `req_time=T`.
4. Between `req_time=T` being stamped and `_should_fetch` running, an unrelated scope's fetch updates the shared key to `T+ε`.
5. `_was_fetched_after(T)` returns True → fetch is skipped.
6. `_notify_on_changes` reads `origin/<branch>` from the local clone — it still points to `C1` (the previous fetch's tip on this source), not `C2`.
7. OPAL publishes a notification for `C1`: newer than `old_revision`, but missing the actual latest `C2`.

### Note on the secondary concern (tracked separately)
[git_fetcher.py:237-241](../../packages/opal-server/opal_server/git_fetcher.py#L237-L241) caches `pygit2.Repository` per-path. In a multi-worker process model, each worker has its own in-memory cache; pygit2's loose/packed-ref cache may briefly return stale ref pointers after another worker fetches. This is a separate issue; this plan does not address it.

---

## File Structure

- Modify: [packages/opal-server/opal_server/git_fetcher.py](../../packages/opal-server/opal_server/git_fetcher.py) — compute `self._source_id` once in `__init__`; use it in `_was_fetched_after` and the fetch-time write.
- Create: `packages/opal-server/opal_server/tests/test_git_fetcher_repos_last_fetched.py` — regression test that two distinct sources do not collide in `repos_last_fetched`.

---

## Task 1: Regression test for per-source `repos_last_fetched` keying

**Files:**
- Create: `packages/opal-server/opal_server/tests/test_git_fetcher_repos_last_fetched.py`

- [ ] **Step 1: Write the failing test**

```python
import datetime
from pathlib import Path

import pytest

from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_server.git_fetcher import GitPolicyFetcher


def _make_fetcher(scope_id: str, url: str, branch: str = "main") -> GitPolicyFetcher:
    source = GitPolicyScopeSource(url=url, branch=branch)
    return GitPolicyFetcher(
        base_dir=Path("/tmp/opal-test"),
        scope_id=scope_id,
        source=source,
    )


@pytest.fixture(autouse=True)
def _reset_class_state():
    GitPolicyFetcher.repos_last_fetched.clear()
    yield
    GitPolicyFetcher.repos_last_fetched.clear()


@pytest.mark.asyncio
async def test_was_fetched_after_is_per_source():
    """A recent fetch on source X must not cause source Y's refresh to be skipped."""
    fetcher_x = _make_fetcher("scope_x", "https://example.com/repo-x.git")
    fetcher_y = _make_fetcher("scope_y", "https://example.com/repo-y.git")

    now = datetime.datetime.now()
    GitPolicyFetcher.repos_last_fetched[
        GitPolicyFetcher.source_id(fetcher_x._source)
    ] = now + datetime.timedelta(seconds=1)

    assert await fetcher_x._was_fetched_after(now) is True
    assert await fetcher_y._was_fetched_after(now) is False


@pytest.mark.asyncio
async def test_repos_last_fetched_keyed_by_source_string():
    """Keys in repos_last_fetched must be the per-source hash string, not a function object."""
    fetcher = _make_fetcher("scope_x", "https://example.com/repo-x.git")
    expected_key = GitPolicyFetcher.source_id(fetcher._source)

    GitPolicyFetcher.repos_last_fetched[expected_key] = datetime.datetime.now()

    assert expected_key in GitPolicyFetcher.repos_last_fetched
    assert isinstance(expected_key, str)
    assert all(isinstance(k, str) for k in GitPolicyFetcher.repos_last_fetched)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/opal-server/opal_server/tests/test_git_fetcher_repos_last_fetched.py -v`
Expected: `test_was_fetched_after_is_per_source` FAILS — `fetcher_y._was_fetched_after(now)` returns True because both fetchers share the unbound-staticmethod key.

## Task 2: Cache the source id at construction time

**Files:**
- Modify: `packages/opal-server/opal_server/git_fetcher.py:122-139` (constructor)

- [ ] **Step 1: Add `self._source_id` in `__init__`**

In `GitPolicyFetcher.__init__`, after computing `self._repo_path`, add:

```python
self._source_id = GitPolicyFetcher.source_id(self._source)
```

Final block:

```python
def __init__(
    self,
    base_dir: Path,
    scope_id: str,
    source: GitPolicyScopeSource,
    callbacks=PolicyFetcherCallbacks(),
    remote_name: str = "origin",
):
    super().__init__(callbacks)
    self._base_dir = GitPolicyFetcher.base_dir(base_dir)
    self._source = source
    self._auth_callbacks = GitCallback(self._source)
    self._repo_path = GitPolicyFetcher.repo_clone_path(base_dir, self._source)
    self._source_id = GitPolicyFetcher.source_id(self._source)
    self._remote = remote_name
    self._scope_id = scope_id
    logger.debug(
        f"Initializing git fetcher: scope_id={scope_id}, url={source.url}, branch={self._source.branch}, path={self._source_id}"
    )
```

(The `path={...}` log argument is updated to use the new attribute, replacing the previously-correct but redundant `GitPolicyFetcher.source_id(source)` call.)

## Task 3: Use the cached source id in the dedup cache

**Files:**
- Modify: `packages/opal-server/opal_server/git_fetcher.py:150-154` (`_was_fetched_after`)
- Modify: `packages/opal-server/opal_server/git_fetcher.py:190-192` (write site in `fetch_and_notify_on_changes`)

- [ ] **Step 1: Fix `_was_fetched_after`**

Replace:
```python
async def _was_fetched_after(self, t: datetime.datetime):
    last_fetched = GitPolicyFetcher.repos_last_fetched.get(self.source_id, None)
    if last_fetched is None:
        return False
    return last_fetched > t
```

With:
```python
async def _was_fetched_after(self, t: datetime.datetime):
    last_fetched = GitPolicyFetcher.repos_last_fetched.get(self._source_id, None)
    if last_fetched is None:
        return False
    return last_fetched > t
```

- [ ] **Step 2: Fix the write site**

Replace:
```python
GitPolicyFetcher.repos_last_fetched[
    self.source_id
] = datetime.datetime.now()
```

With:
```python
GitPolicyFetcher.repos_last_fetched[
    self._source_id
] = datetime.datetime.now()
```

- [ ] **Step 3: Reuse the cached id in `_get_repo_lock` for consistency**

Replace the body of `_get_repo_lock`:

```python
async def _get_repo_lock(self):
    src_id = GitPolicyFetcher.source_id(self._source)
    lock = GitPolicyFetcher.repo_locks[src_id] = GitPolicyFetcher.repo_locks.get(
        src_id, asyncio.Lock()
    )
    return lock
```

With:

```python
async def _get_repo_lock(self):
    lock = GitPolicyFetcher.repo_locks[self._source_id] = GitPolicyFetcher.repo_locks.get(
        self._source_id, asyncio.Lock()
    )
    return lock
```

- [ ] **Step 4: Run the regression test to verify it now passes**

Run: `pytest packages/opal-server/opal_server/tests/test_git_fetcher_repos_last_fetched.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Run the existing git_fetcher / scopes test suites to make sure nothing else breaks**

Run: `pytest packages/opal-server/opal_server/tests -v -k "git_fetcher or scopes"`
Expected: no new failures.

## Task 4: Commit

- [ ] **Step 1: Commit the fix and test together**

```bash
git add packages/opal-server/opal_server/git_fetcher.py \
        packages/opal-server/opal_server/tests/test_git_fetcher_repos_last_fetched.py
git commit -m "fix(opal-server): key repos_last_fetched per source, not by staticmethod ref

self.source_id returns the unbound staticmethod function object (same across
every instance), so repos_last_fetched was a single-entry dict shared by all
sources. A recent fetch on one source could satisfy _was_fetched_after for an
unrelated source's refresh, causing the fetch to be skipped and the
subsequent notification to publish a stale (newer-than-previous but not
latest) commit. Cache the per-source hash once in __init__ and use it
consistently at all call sites. Adds a regression test.
"
```
