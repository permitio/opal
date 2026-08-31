"""Bounded LRU for the process-global pygit2 handle cache.

The production shape this encodes: ``GitPolicyFetcher.repos`` is keyed per clone
path and, before this change, had no size bound, no TTL and exactly one runtime
eviction path -- a scope purge (delete/repoint). On prod-us-east that path is
effectively never taken: 43,026 scopes, net +5 over six hours, one purge-related
log line in the same window. So every scope a worker touched pinned a
``pygit2.Repository`` -- open fds and mmapped pack indexes -- for the life of the
process, and RSS climbed ~129 MB/h with no plateau.

It did not reproduce on the staging bed because the bed had 40 repos (the cache
saturates at 40 entries and cannot grow) and its leak test was hours of
create/delete churn, which exercises the purge path continuously. High-churn /
low-cardinality hid it; prod is zero-churn / high-cardinality.

Each test names, in its docstring, the mutation it catches.
"""
import pytest
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher

# Small enough that the LRU arithmetic is readable; nothing here depends on the
# shipped default.
_CAP = 3


class _FakeRepo:
    """Stands in for pygit2.Repository.

    ``free()`` is the call that actually
    releases fds and mmapped pack indexes, so the tests assert on it.
    """

    def __init__(self, name: str):
        self.name = name
        self.freed = False

    def free(self) -> None:
        self.freed = True


@pytest.fixture(autouse=True)
def _reset_class_state(monkeypatch):
    """Repos is process-global class state -- a leaked entry would make a later
    test pass for the wrong reason."""
    for d in (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
        GitPolicyFetcher.source_backoff,
    ):
        d.clear()
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_HANDLE_CACHE_SIZE", _CAP)
    yield
    for d in (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
        GitPolicyFetcher.source_backoff,
    ):
        d.clear()


def _put(path: str) -> _FakeRepo:
    """Insert through the same helper the clone and open paths use, so the test
    exercises the real admission + eviction sequence."""
    repo = _FakeRepo(path)
    GitPolicyFetcher.cache_repo(path, repo)
    return repo


def _paths():
    return list(GitPolicyFetcher.repos)


def test_cache_is_bounded_by_the_configured_cap():
    """Catches removing the eviction call from cache_repo: without it the dict
    grows to one entry per source touched, which is the prod leak."""
    for i in range(10):
        _put(f"/clones/s{i}")

    assert len(GitPolicyFetcher.repos) == _CAP


def test_eviction_is_least_recently_used_not_insertion_order():
    """Catches evicting by insertion order: re-reading an old source must renew
    it, or a hot repo touched every pass gets dropped while a cold one survives."""
    a, b, c = (_put(f"/clones/{n}") for n in ("a", "b", "c"))

    # Touch 'a' through the read path so it becomes the most recent.
    GitPolicyFetcher.touch_repo("/clones/a")
    _put("/clones/d")

    assert "/clones/a" in _paths(), "renewed entry was evicted"
    assert "/clones/b" not in _paths(), "true LRU victim survived"
    assert b.freed is True
    assert a.freed is False


def test_eviction_frees_the_handle():
    """Catches evicting with a bare dict pop: dropping the reference without
    free() leaves fds and mmapped pack indexes pinned until GC, which is the
    resource this change exists to reclaim."""
    victim = _put("/clones/victim")
    for i in range(_CAP):
        _put(f"/clones/keep{i}")

    assert "/clones/victim" not in _paths()
    assert victim.freed is True


def test_never_evicts_a_source_with_a_git_op_in_flight(monkeypatch):
    """Catches dropping the in-flight guard: free()ing a handle a pool thread is
    still reading is a use-after-free. The entry may stay over cap -- correctness
    outranks the bound."""
    monkeypatch.setattr(
        "opal_server.git_fetcher.git_op_in_flight",
        lambda source_id: source_id == "busy",
    )
    busy = _put("/clones/busy")
    for i in range(_CAP + 2):
        _put(f"/clones/idle{i}")

    assert "/clones/busy" in _paths(), "evicted a handle with a git op in flight"
    assert busy.freed is False


def test_never_evicts_the_entry_just_admitted(monkeypatch):
    """Catches evicting without protecting the new entry: at cap 1 the caller
    would get back a handle that was freed on the way out."""
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_HANDLE_CACHE_SIZE", 1)
    _put("/clones/first")
    fresh = _put("/clones/second")

    assert _paths() == ["/clones/second"]
    assert fresh.freed is False


def test_zero_disables_the_bound(monkeypatch):
    """Catches treating 0 as 'evict everything'.

    0 is the documented escape hatch back to the pre-change unbounded
    behaviour.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_HANDLE_CACHE_SIZE", 0)
    for i in range(50):
        _put(f"/clones/s{i}")

    assert len(GitPolicyFetcher.repos) == 50


def test_purge_still_evicts_regardless_of_cap():
    """Catches making the cap the only eviction path: forget_repo is what the
    scope purge calls, and it must keep working for a deleted source."""
    repo = _put("/clones/gone")
    GitPolicyFetcher.forget_repo("/clones/gone")

    assert "/clones/gone" not in _paths()
    assert repo.freed is True
