"""
Tests for GitPolicyFetcher cleanup behavior when GitHub is down (issue #634).

These tests verify that Repository objects are properly cleaned up from cache
and file descriptors are released when Git operations fail, preventing symbolic
links from accumulating in /proc.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pygit2

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks
from opal_common.schemas.policy_source import GitPolicyScopeSource


@pytest.fixture
def tmp_base_dir(tmp_path):
    """Create a temporary base directory for git repositories."""
    return tmp_path / "git_sources"


@pytest.fixture
def mock_git_source():
    """Create a mock GitPolicyScopeSource."""
    return GitPolicyScopeSource(
        url="https://github.com/test/repo.git",
        branch="main",
        directories=["."],
    )


@pytest.fixture
def git_fetcher(tmp_base_dir, mock_git_source):
    """Create a GitPolicyFetcher instance for testing."""
    return GitPolicyFetcher(
        base_dir=tmp_base_dir,
        scope_id="test-scope",
        source=mock_git_source,
        callbacks=PolicyFetcherCallbacks(),
    )


class TestGitFetcherCleanup:
    """Test cleanup behavior when Git operations fail."""

    @pytest.mark.asyncio
    async def test_cleanup_repo_from_cache_on_fetch_failure(self, git_fetcher, tmp_base_dir):
        """Test that Repository is removed from cache when fetch fails."""
        # Create a mock repository path
        repo_path = tmp_base_dir / "test-repo"
        repo_path.mkdir(parents=True)
        (repo_path / ".git").mkdir()
        
        # Create a mock Repository object and add it to cache
        mock_repo = MagicMock(spec=pygit2.Repository)
        GitPolicyFetcher.repos[str(repo_path)] = mock_repo
        
        # Verify repo is in cache
        assert str(repo_path) in GitPolicyFetcher.repos
        
        # Mock _discover_repository to return True
        git_fetcher._discover_repository = lambda path: True
        
        # Mock _get_valid_repo to return the mock repo
        git_fetcher._get_valid_repo = lambda: mock_repo
        
        # Mock _should_fetch to return True
        git_fetcher._should_fetch = lambda *args, **kwargs: True
        
        # Mock fetch to raise GitError (simulating GitHub being down)
        mock_remote = MagicMock()
        mock_remote.fetch.side_effect = pygit2.GitError("GitHub returned 500")
        mock_repo.remotes = {"origin": mock_remote}
        
        # Attempt fetch - should raise GitError and clean up cache
        with pytest.raises(pygit2.GitError):
            await git_fetcher.fetch_and_notify_on_changes(force_fetch=True)
        
        # Verify repo was removed from cache
        assert str(repo_path) not in GitPolicyFetcher.repos, \
            "Repository should be removed from cache after fetch failure"

    @pytest.mark.asyncio
    async def test_cleanup_repo_from_cache_on_clone_failure(self, git_fetcher, tmp_base_dir):
        """Test that Repository is removed from cache and partial repo is cleaned up when clone fails."""
        repo_path = git_fetcher._repo_path
        
        # Mock clone_repository to raise GitError (simulating GitHub being down)
        with patch("opal_server.git_fetcher.clone_repository") as mock_clone:
            mock_clone.side_effect = pygit2.GitError("GitHub returned 500")
            
            # Create a partial repository directory (simulating failed clone)
            repo_path.mkdir(parents=True, exist_ok=True)
            (repo_path / "partial_file.txt").write_text("partial content")
            
            # Verify partial directory exists
            assert repo_path.exists()
            
            # Attempt clone - should raise GitError and clean up
            with pytest.raises(pygit2.GitError):
                await git_fetcher._clone()
            
            # Verify partial repository was cleaned up
            assert not repo_path.exists(), \
                "Partial repository directory should be cleaned up after clone failure"
            
            # Verify repo was removed from cache (if it was there)
            assert str(repo_path) not in GitPolicyFetcher.repos, \
                "Repository should not be in cache after clone failure"

    @pytest.mark.asyncio
    async def test_cleanup_repo_from_cache_on_invalid_repo(self, git_fetcher, tmp_base_dir):
        """Test that Repository is removed from cache when repo is invalid."""
        repo_path = git_fetcher._repo_path
        repo_path.mkdir(parents=True)
        (repo_path / ".git").mkdir()
        
        # Create a mock Repository object and add it to cache
        mock_repo = MagicMock(spec=pygit2.Repository)
        GitPolicyFetcher.repos[str(repo_path)] = mock_repo
        
        # Verify repo is in cache
        assert str(repo_path) in GitPolicyFetcher.repos
        
        # Mock _discover_repository to return True
        git_fetcher._discover_repository = lambda path: True
        
        # Mock _get_valid_repo to raise GitError (invalid repo)
        git_fetcher._get_valid_repo = lambda: None
        
        # Mock _get_repo to return mock_repo that raises on verification
        original_get_repo = git_fetcher._get_repo
        def mock_get_repo():
            repo = original_get_repo()
            # Simulate verification failure
            raise pygit2.GitError("Invalid repository")
        git_fetcher._get_repo = mock_get_repo
        
        # Call fetch_and_notify_on_changes - should clean up invalid repo
        await git_fetcher.fetch_and_notify_on_changes()
        
        # Verify repo was removed from cache
        assert str(repo_path) not in GitPolicyFetcher.repos, \
            "Invalid repository should be removed from cache"

    def test_cleanup_repo_from_cache_method(self, git_fetcher, tmp_base_dir):
        """Test the _cleanup_repo_from_cache method directly."""
        repo_path = git_fetcher._repo_path
        
        # Add a mock repo to cache
        mock_repo = MagicMock(spec=pygit2.Repository)
        GitPolicyFetcher.repos[str(repo_path)] = mock_repo
        
        # Verify repo is in cache
        assert str(repo_path) in GitPolicyFetcher.repos
        
        # Call cleanup method
        git_fetcher._cleanup_repo_from_cache()
        
        # Verify repo was removed from cache
        assert str(repo_path) not in GitPolicyFetcher.repos, \
            "Repository should be removed from cache by cleanup method"
        
        # Call cleanup again (should not error if already removed)
        git_fetcher._cleanup_repo_from_cache()
        
        # Verify still not in cache
        assert str(repo_path) not in GitPolicyFetcher.repos

    @pytest.mark.asyncio
    async def test_cleanup_before_deleting_invalid_repo_directory(self, git_fetcher, tmp_base_dir):
        """Test that cache is cleaned up before deleting invalid repo directory."""
        repo_path = git_fetcher._repo_path
        repo_path.mkdir(parents=True)
        (repo_path / ".git").mkdir()
        
        # Create a mock Repository object and add it to cache
        mock_repo = MagicMock(spec=pygit2.Repository)
        GitPolicyFetcher.repos[str(repo_path)] = mock_repo
        
        # Verify repo is in cache
        assert str(repo_path) in GitPolicyFetcher.repos
        
        # Mock _discover_repository to return True
        git_fetcher._discover_repository = lambda path: True
        
        # Mock _get_valid_repo to return None (invalid repo)
        git_fetcher._get_valid_repo = lambda: None
        
        # Call fetch_and_notify_on_changes - should clean up and delete directory
        await git_fetcher.fetch_and_notify_on_changes()
        
        # Verify repo was removed from cache BEFORE directory deletion
        assert str(repo_path) not in GitPolicyFetcher.repos, \
            "Repository should be removed from cache before directory deletion"
        
        # Verify directory was deleted
        assert not repo_path.exists(), \
            "Invalid repository directory should be deleted"

    def test_multiple_cleanup_calls_safe(self, git_fetcher):
        """Test that multiple cleanup calls are safe (idempotent)."""
        # Call cleanup multiple times - should not error
        git_fetcher._cleanup_repo_from_cache()
        git_fetcher._cleanup_repo_from_cache()
        git_fetcher._cleanup_repo_from_cache()
        
        # Should complete without error
        assert True
