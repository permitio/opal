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
