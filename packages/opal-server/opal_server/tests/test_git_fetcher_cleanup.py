"""Tests for GitPolicyFetcher cleanup on git operation failures (issue #634).

Verifies that Repository objects are freed and removed from cache when
git operations fail, preventing file descriptor / symlink leaks in /proc.
"""

import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# We mock pygit2 at import-time so the test suite can run without it installed.
pygit2_mock = MagicMock()
pygit2_mock.GitError = type("GitError", (Exception,), {})

import sys

sys.modules.setdefault("pygit2", pygit2_mock)

from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fetcher(tmp_path: Path, url="https://github.com/test/repo.git", branch="main"):
    """Create a GitPolicyFetcher with a temporary base directory."""
    source = MagicMock()
    source.url = url
    source.branch = branch
    source.auth = None
    source.directories = ["."]
    source.extensions = [".rego"]
    source.manifest = None
    source.bundle_ignore = None

    fetcher = GitPolicyFetcher(
        base_dir=tmp_path,
        scope_id="test-scope",
        source=source,
        callbacks=PolicyFetcherCallbacks(),
    )
    return fetcher


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCleanupRepoFromCache:
    def test_removes_repo_from_cache_and_frees(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        mock_repo = MagicMock()
        GitPolicyFetcher.repos[str(fetcher._repo_path)] = mock_repo

        fetcher._cleanup_repo_from_cache()

        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos
        mock_repo.free.assert_called_once()

    def test_idempotent(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        # Call twice – second call should be a no-op
        fetcher._cleanup_repo_from_cache()
        fetcher._cleanup_repo_from_cache()

    def test_survives_free_raising(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        mock_repo = MagicMock()
        mock_repo.free.side_effect = RuntimeError("boom")
        GitPolicyFetcher.repos[str(fetcher._repo_path)] = mock_repo

        fetcher._cleanup_repo_from_cache()  # should not raise
        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos


class TestCloneCleanup:
    @pytest.mark.asyncio
    async def test_partial_dir_removed_on_clone_failure(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        repo_path = fetcher._repo_path
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "partial").touch()

        with patch("opal_server.git_fetcher.run_sync", side_effect=pygit2_mock.GitError("down")):
            await fetcher._clone()

        assert not repo_path.exists(), "partial clone dir should be removed"

    @pytest.mark.asyncio
    async def test_cache_cleaned_on_clone_failure(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        mock_repo = MagicMock()
        GitPolicyFetcher.repos[str(fetcher._repo_path)] = mock_repo

        with patch("opal_server.git_fetcher.run_sync", side_effect=pygit2_mock.GitError("down")):
            await fetcher._clone()

        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos


class TestFetchCleanup:
    @pytest.mark.asyncio
    async def test_cache_cleaned_on_fetch_failure(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        repo_path = fetcher._repo_path
        repo_path.mkdir(parents=True)
        (repo_path / ".git").mkdir()

        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_remote.fetch.side_effect = pygit2_mock.GitError("500")
        mock_repo.remotes = {"origin": mock_remote}
        GitPolicyFetcher.repos[str(repo_path)] = mock_repo

        # Patch helpers so we reach the fetch path
        fetcher._discover_repository = lambda p: True
        fetcher._get_valid_repo = lambda: mock_repo

        async def _fake_should_fetch(*a, **kw):
            return True
        fetcher._should_fetch = _fake_should_fetch

        with patch("opal_server.git_fetcher.run_sync", side_effect=pygit2_mock.GitError("500")):
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)

        assert str(repo_path) not in GitPolicyFetcher.repos


class TestInvalidRepoCleanup:
    def test_get_valid_repo_cleans_cache(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        mock_repo = MagicMock()
        GitPolicyFetcher.repos[str(fetcher._repo_path)] = mock_repo

        # Make Repository() constructor raise
        with patch("opal_server.git_fetcher.Repository", side_effect=pygit2_mock.GitError("corrupt")):
            result = fetcher._get_valid_repo()

        assert result is None
        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos
