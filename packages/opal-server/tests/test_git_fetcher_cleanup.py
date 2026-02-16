"""Tests for git_fetcher cleanup and cache invalidation (issue #634).

Verifies that:
- Failed clone operations clean up partial directories and broken symlinks.
- Fetch failures (e.g. GitHub down) are handled gracefully with cleanup.
- Invalid repos are removed from the class-level cache.
"""

import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pygit2
import pytest

from opal_server.git_fetcher import GitPolicyFetcher


def _make_fetcher(tmp_path: Path) -> GitPolicyFetcher:
    """Create a GitPolicyFetcher with a minimal mock source."""
    source = MagicMock()
    source.url = "https://github.com/example/repo.git"
    source.branch = "main"
    source.auth = None

    fetcher = GitPolicyFetcher(
        base_dir=tmp_path,
        scope_id="test-scope",
        source=source,
        callbacks=MagicMock(),
    )
    return fetcher


class TestCloneCleanup:
    """_clone() must clean up self._repo_path when clone_repository fails."""

    @pytest.mark.asyncio
    async def test_clone_failure_removes_partial_directory(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)

        # Simulate a partial directory left by a failed clone
        fetcher._repo_path.mkdir(parents=True, exist_ok=True)
        (fetcher._repo_path / "partial_file").touch()

        with patch(
            "opal_server.git_fetcher.run_sync",
            side_effect=pygit2.GitError("connection refused"),
        ):
            await fetcher._clone()

        assert not fetcher._repo_path.exists(), (
            "Partial repo directory should be removed after clone failure"
        )

    @pytest.mark.asyncio
    async def test_clone_failure_removes_broken_symlink(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)

        # Create a broken symlink at repo_path
        target = tmp_path / "nonexistent_target"
        fetcher._repo_path.symlink_to(target)
        assert fetcher._repo_path.is_symlink()

        with patch(
            "opal_server.git_fetcher.run_sync",
            side_effect=pygit2.GitError("connection refused"),
        ):
            await fetcher._clone()

        assert not fetcher._repo_path.is_symlink(), (
            "Broken symlink should be removed after clone failure"
        )

    @pytest.mark.asyncio
    async def test_clone_failure_invalidates_cache(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        path_key = str(fetcher._repo_path)
        source_id = GitPolicyFetcher.source_id(fetcher._source)

        # Pre-populate the cache
        GitPolicyFetcher.repos[path_key] = MagicMock()
        GitPolicyFetcher.repos_last_fetched[source_id] = "some-time"

        with patch(
            "opal_server.git_fetcher.run_sync",
            side_effect=pygit2.GitError("connection refused"),
        ):
            await fetcher._clone()

        assert path_key not in GitPolicyFetcher.repos
        assert source_id not in GitPolicyFetcher.repos_last_fetched


class TestFetchFailureCleanup:
    """fetch_and_notify_on_changes() must handle fetch errors gracefully."""

    @pytest.mark.asyncio
    async def test_fetch_failure_cleans_up_and_invalidates(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        path_key = str(fetcher._repo_path)

        # Create a fake repo directory with .git so _discover_repository passes
        (fetcher._repo_path / ".git").mkdir(parents=True, exist_ok=True)

        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_remote.fetch.side_effect = pygit2.GitError("GitHub is down")
        mock_repo.remotes = {fetcher._remote: mock_remote}

        GitPolicyFetcher.repos[path_key] = mock_repo

        with (
            patch.object(fetcher, "_discover_repository", return_value=True),
            patch.object(fetcher, "_get_valid_repo", return_value=mock_repo),
            patch.object(fetcher, "_should_fetch", return_value=True),
            patch(
                "opal_server.git_fetcher.run_sync",
                side_effect=pygit2.GitError("GitHub is down"),
            ),
        ):
            # Should not raise
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)

        assert path_key not in GitPolicyFetcher.repos, (
            "Failed repo should be removed from cache"
        )
        assert not fetcher._repo_path.exists(), (
            "Repo directory should be cleaned up after fetch failure"
        )


class TestCacheInvalidation:
    """Invalid repos must be evicted from GitPolicyFetcher.repos."""

    @pytest.mark.asyncio
    async def test_invalid_repo_removed_from_cache_on_discovery(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        path_key = str(fetcher._repo_path)

        # Simulate: directory exists but repo is invalid
        (fetcher._repo_path / ".git").mkdir(parents=True, exist_ok=True)
        GitPolicyFetcher.repos[path_key] = MagicMock()

        mock_clone_repo = MagicMock()

        with (
            patch.object(fetcher, "_discover_repository", return_value=True),
            patch.object(fetcher, "_get_valid_repo", return_value=None),
            patch.object(fetcher, "_clone", new_callable=AsyncMock) as mock_clone,
        ):
            await fetcher.fetch_and_notify_on_changes()
            mock_clone.assert_called_once()

        assert path_key not in GitPolicyFetcher.repos, (
            "Invalid repo should be evicted from cache"
        )

    def test_cleanup_repo_path_is_idempotent(self, tmp_path):
        """Calling _cleanup_repo_path on a non-existent path should not raise."""
        nonexistent = tmp_path / "does_not_exist"
        GitPolicyFetcher._cleanup_repo_path(nonexistent)  # should not raise

    def test_invalidate_repo_cache_is_safe_when_empty(self, tmp_path):
        """_invalidate_repo_cache should not raise even if caches are empty."""
        fetcher = _make_fetcher(tmp_path)
        fetcher._invalidate_repo_cache()  # should not raise
