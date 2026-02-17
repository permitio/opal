"""Tests for GitPolicyFetcher cleanup on git operation failures (issue #634).

Verifies that Repository objects are freed and removed from cache when
git operations fail, preventing file descriptor / symlink leaks in /proc.
"""

import asyncio
import os
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys

# Mock fcntl for Windows compatibility (fcntl is Unix-only)
if os.name == 'nt':
    sys.modules.setdefault("fcntl", MagicMock())

# We mock pygit2 at import-time so the test suite can run without it installed.
pygit2_mock = MagicMock()
pygit2_mock.GitError = type("GitError", (Exception,), {})
sys.modules.setdefault("pygit2", pygit2_mock)

from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fetcher(tmp_path: Path, url="https://github.com/test/repo.git", branch="main"):
    """Create a GitPolicyFetcher with a temporary base directory."""
    # Create a proper source mock that won't cause StopIteration
    source = MagicMock(spec=['url', 'branch', 'auth', 'directories', 'extensions', 'manifest', 'bundle_ignore'])
    source.url = url
    source.branch = branch
    source.auth = None
    source.directories = ["."]
    source.extensions = [".rego"]
    source.manifest = None
    source.bundle_ignore = None
    
    # Mock GitCallback to avoid issues with RemoteCallbacks
    with patch("opal_server.git_fetcher.GitCallback", return_value=MagicMock()):
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
        """Test that cleanup method removes from cache and calls repo.free()."""
        fetcher = _make_fetcher(tmp_path)
        mock_repo = MagicMock()
        GitPolicyFetcher.repos[str(fetcher._repo_path)] = mock_repo

        fetcher._cleanup_repo_from_cache()

        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos
        mock_repo.free.assert_called_once()

    def test_idempotent(self, tmp_path):
        """Test that multiple cleanup calls are safe (idempotent)."""
        fetcher = _make_fetcher(tmp_path)
        # Call twice – second call should be a no-op
        fetcher._cleanup_repo_from_cache()
        fetcher._cleanup_repo_from_cache()

    def test_survives_free_raising(self, tmp_path):
        """Test that cleanup handles errors during repo.free() gracefully."""
        fetcher = _make_fetcher(tmp_path)
        mock_repo = MagicMock()
        mock_repo.free.side_effect = RuntimeError("boom")
        GitPolicyFetcher.repos[str(fetcher._repo_path)] = mock_repo

        fetcher._cleanup_repo_from_cache()  # should not raise
        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos


class TestCloneCleanup:
    @pytest.mark.asyncio
    async def test_partial_dir_removed_on_clone_failure(self, tmp_path):
        """Test that partial directory is removed when clone fails."""
        fetcher = _make_fetcher(tmp_path)
        repo_path = fetcher._repo_path
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "partial").touch()

        with patch("opal_server.git_fetcher.run_sync", side_effect=pygit2_mock.GitError("down")):
            await fetcher._clone()

        assert not repo_path.exists(), "partial clone dir should be removed"

    @pytest.mark.asyncio
    async def test_cache_cleaned_on_clone_failure(self, tmp_path):
        """Test that cache is cleaned when clone fails."""
        fetcher = _make_fetcher(tmp_path)
        mock_repo = MagicMock()
        GitPolicyFetcher.repos[str(fetcher._repo_path)] = mock_repo

        with patch("opal_server.git_fetcher.run_sync", side_effect=pygit2_mock.GitError("down")):
            await fetcher._clone()

        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos


class TestFetchCleanup:
    @pytest.mark.asyncio
    async def test_cache_cleaned_on_fetch_failure(self, tmp_path):
        """Test that cache is cleaned when fetch fails (main scenario for #634)."""
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
            with pytest.raises(pygit2_mock.GitError):
                await fetcher.fetch_and_notify_on_changes(force_fetch=True)

        assert str(repo_path) not in GitPolicyFetcher.repos


class TestInvalidRepoCleanup:
    def test_get_valid_repo_cleans_cache(self, tmp_path):
        """Test that _get_valid_repo cleans cache when repo is invalid."""
        fetcher = _make_fetcher(tmp_path)
        
        # Make Repository() constructor raise GitError when called
        with patch("opal_server.git_fetcher.Repository", side_effect=pygit2_mock.GitError("corrupt")):
            result = fetcher._get_valid_repo()

        assert result is None
        assert str(fetcher._repo_path) not in GitPolicyFetcher.repos


class TestDeleteInvalidRepoCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_before_deleting_invalid_repo_directory(self, tmp_path):
        """Test that cache is cleaned before deleting invalid repo directory."""
        fetcher = _make_fetcher(tmp_path)
        repo_path = fetcher._repo_path
        repo_path.mkdir(parents=True)
        (repo_path / ".git").mkdir()

        mock_repo = MagicMock()
        GitPolicyFetcher.repos[str(repo_path)] = mock_repo

        # Mock _discover_repository to return True
        fetcher._discover_repository = lambda path: True

        # Mock _get_valid_repo to return None (invalid repo)
        fetcher._get_valid_repo = lambda: None

        # Mock _clone to avoid actual cloning
        async def mock_clone():
            pass
        fetcher._clone = mock_clone

        # Call fetch_and_notify_on_changes - should clean up and delete directory
        await fetcher.fetch_and_notify_on_changes()

        # Verify repo was removed from cache BEFORE directory deletion
        assert str(repo_path) not in GitPolicyFetcher.repos, \
            "Repository should be removed from cache before directory deletion"

        # Verify directory was deleted
        assert not repo_path.exists(), \
            "Invalid repository directory should be deleted"
