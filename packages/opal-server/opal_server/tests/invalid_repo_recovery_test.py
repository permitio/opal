from pathlib import Path

import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server.git_fetcher import GitPolicyFetcher


def _make_fetcher(base_dir: Path, scope_id: str, url: str) -> GitPolicyFetcher:
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="main",
        auth=NoAuthData(auth_type="none"),
    )
    return GitPolicyFetcher(base_dir=base_dir, scope_id=scope_id, source=source)


@pytest.fixture(autouse=True)
def _reset_class_state():
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    yield
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()


class _BrokenRepo:
    """Simulates a cached pygit2 handle whose backing clone dir went bad."""

    freed = False

    @property
    def remotes(self):
        raise pygit2.GitError("stale handle: backing files gone")

    def free(self):
        self.freed = True


@pytest.mark.asyncio
async def test_recovery_forgets_stale_cached_handle(monkeypatch, tmp_path):
    """Bug A: without forget_repo in the recovery branch, the broken cached
    handle survives and re-invalidates every fresh clone -> infinite loop."""
    fetcher = _make_fetcher(tmp_path, "s", "https://example.com/r.git")
    path = str(fetcher._repo_path)
    broken = _BrokenRepo()
    GitPolicyFetcher.repos[path] = broken
    monkeypatch.setattr(fetcher, "_discover_repository", lambda p: True)
    monkeypatch.setattr("opal_server.git_fetcher.shutil.rmtree", lambda p, **k: None)
    clone_calls = []

    async def fake_clone():
        clone_calls.append(True)

    monkeypatch.setattr(fetcher, "_clone", fake_clone)

    await fetcher.fetch_and_notify_on_changes()

    assert clone_calls == [True]
    assert GitPolicyFetcher.repos.get(path) is not broken, (
        "recovery left the stale handle cached — next sync re-invalidates "
        "the fresh clone (infinite re-clone loop)"
    )
    assert broken.freed is True, "recovery evicted the handle without free()ing it"


@pytest.mark.asyncio
async def test_clone_caches_the_fresh_handle(monkeypatch, tmp_path):
    fetcher = _make_fetcher(tmp_path, "s", "https://example.com/r.git")
    fresh = object()
    monkeypatch.setattr(
        "opal_server.git_fetcher.clone_repository", lambda *a, **k: fresh
    )

    async def _no_notify(repo):
        return None

    monkeypatch.setattr(fetcher, "_notify_on_changes", _no_notify)

    await fetcher._clone()

    assert GitPolicyFetcher.repos.get(str(fetcher._repo_path)) is fresh, (
        "fresh clone's handle not cached — _get_repo would reopen (or worse, "
        "return a stale entry) on the next sync"
    )


@pytest.mark.asyncio
async def test_clone_clears_partial_dir_before_cloning(monkeypatch, tmp_path):
    """U9: a failed clone leaves a partial dir; clone_repository refuses a
    non-empty destination, wedging every retry."""
    fetcher = _make_fetcher(tmp_path, "s", "https://example.com/r.git")
    fetcher._repo_path.mkdir(parents=True)
    (fetcher._repo_path / "leftover.pack").write_text("partial clone debris")
    seen = {}

    def fake_clone(url, path, callbacks=None):
        p = Path(path)
        seen["nonempty"] = p.exists() and any(p.iterdir())
        return object()

    monkeypatch.setattr("opal_server.git_fetcher.clone_repository", fake_clone)

    async def _no_notify(repo):
        return None

    monkeypatch.setattr(fetcher, "_notify_on_changes", _no_notify)

    await fetcher._clone()

    assert seen["nonempty"] is False, (
        "partial dir not cleared before clone — a real clone_repository "
        "raises on a non-empty destination, wedging the scope forever"
    )


class _RemoteStub:
    def __init__(self, url):
        self.url = url
        self.name = "origin"


class _Ref:
    target = "deadbeef" * 5


class _WarmHandle:
    """Cached handle over a gutted clone: its open mmaps keep the deleted
    pack files readable (unlink does not invalidate them), so through THIS
    handle the repo looks perfectly healthy."""

    def __init__(self, url):
        self.remotes = [_RemoteStub(url)]
        self.freed = False

    def lookup_reference(self, name):
        return _Ref()

    def get(self, oid):
        return object()  # mmap still serves the object

    def free(self):
        self.freed = True


class _GuttedProbe:
    """What a fresh on-disk handle sees: refs intact, head object missing."""

    def __init__(self, path):
        self.freed = False

    def lookup_reference(self, name):
        return _Ref()

    def get(self, oid):
        return None  # object store gutted on disk

    def free(self):
        self.freed = True


@pytest.mark.asyncio
async def test_gutted_object_store_triggers_recovery(monkeypatch, tmp_path):
    """Refs intact + objects missing on disk must be treated as invalid even
    though the warm cached handle still reads everything via its mmaps:
    fetch would negotiate "up to date" and the scope would serve 500s
    forever otherwise."""
    url = "https://example.com/r.git"
    fetcher = _make_fetcher(tmp_path, "s", url)
    path = str(fetcher._repo_path)
    warm = _WarmHandle(url)
    GitPolicyFetcher.repos[path] = warm
    probes = []

    def fake_repository(p):
        probe = _GuttedProbe(p)
        probes.append(probe)
        return probe

    monkeypatch.setattr("opal_server.git_fetcher.Repository", fake_repository)
    monkeypatch.setattr(fetcher, "_discover_repository", lambda p: True)
    monkeypatch.setattr("opal_server.git_fetcher.shutil.rmtree", lambda p, **k: None)
    clone_calls = []

    async def fake_clone():
        clone_calls.append(True)

    monkeypatch.setattr(fetcher, "_clone", fake_clone)

    await fetcher.fetch_and_notify_on_changes()

    assert clone_calls == [True], "gutted clone was not routed to recovery"
    assert path not in GitPolicyFetcher.repos
    assert warm.freed is True, "recovery evicted the warm handle without free()"
    assert probes and all(p.freed for p in probes), "disk probe handle leaked"


class _PoisonRepo:
    """Any attribute access means the shared cached handle was touched."""

    def __getattr__(self, name):
        raise AssertionError(
            "shared cached handle was read outside lock_source (UAF hazard)"
        )


def test_branch_head_does_not_touch_shared_handle(monkeypatch, tmp_path):
    fetcher = _make_fetcher(tmp_path, "s", "https://example.com/r.git")
    path = str(fetcher._repo_path)
    GitPolicyFetcher.repos[path] = _PoisonRepo()
    fresh = object()
    monkeypatch.setattr("opal_server.git_fetcher.Repository", lambda p: fresh)
    monkeypatch.setattr(
        "opal_server.git_fetcher.RepoInterface.get_commit_hash",
        lambda repo, branch, remote: "abc123" if repo is fresh else None,
    )

    assert fetcher._get_current_branch_head() == "abc123"


class _HealthyCachedRepo:
    """The warm cached handle _get_valid_repo returns when the disk probe
    confirms the repo is healthy."""

    def __init__(self, url):
        self.remotes = [_RemoteStub(url)]
        self.freed = False

    def free(self):
        self.freed = True


class _BranchNotFetchedProbe:
    """Fresh on-disk probe when the tracked branch has never been fetched (e.g.
    right after a scope's remote branch config changed)."""

    def __init__(self, path):
        self.freed = False

    def lookup_reference(self, name):
        raise KeyError(name)

    def free(self):
        self.freed = True


def test_get_valid_repo_tolerates_branch_not_yet_fetched(monkeypatch, tmp_path):
    """The fetch path is responsible for missing branches -- the probe must not
    treat that as corruption and must still return the cached repo."""
    url = "https://example.com/r.git"
    fetcher = _make_fetcher(tmp_path, "s", url)
    path = str(fetcher._repo_path)
    cached = _HealthyCachedRepo(url)
    GitPolicyFetcher.repos[path] = cached
    probes = []

    def fake_repository(p):
        probe = _BranchNotFetchedProbe(p)
        probes.append(probe)
        return probe

    monkeypatch.setattr("opal_server.git_fetcher.Repository", fake_repository)

    result = fetcher._get_valid_repo()

    assert result is cached
    assert probes and all(p.freed for p in probes), "disk probe handle leaked"


class _HealthyProbe:
    """Fresh on-disk probe when the head object is actually readable from disk
    (the healthy case)."""

    def __init__(self, path):
        self.freed = False

    def lookup_reference(self, name):
        return _Ref()

    def get(self, oid):
        return object()  # readable from disk

    def free(self):
        self.freed = True


def test_get_valid_repo_returns_cached_when_probe_confirms_healthy(
    monkeypatch, tmp_path
):
    url = "https://example.com/r.git"
    fetcher = _make_fetcher(tmp_path, "s", url)
    path = str(fetcher._repo_path)
    cached = _HealthyCachedRepo(url)
    GitPolicyFetcher.repos[path] = cached
    probes = []

    def fake_repository(p):
        probe = _HealthyProbe(p)
        probes.append(probe)
        return probe

    monkeypatch.setattr("opal_server.git_fetcher.Repository", fake_repository)

    result = fetcher._get_valid_repo()

    assert result is cached
    assert probes and all(p.freed for p in probes), "disk probe handle leaked"
