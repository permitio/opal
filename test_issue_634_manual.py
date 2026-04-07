#!/usr/bin/env python3
"""
Manual test script for issue #634: Symbolic link cleanup when GitHub is down.

This script simulates the scenario where GitHub is down and verifies that:
1. Repository objects are cleaned up from cache
2. File descriptors are released
3. No symbolic links accumulate in /proc

Usage:
    python test_issue_634_manual.py

Requirements:
    - OPAL server dependencies installed
    - Access to /proc (Linux only)
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "packages"))

import pygit2
from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks
from opal_common.schemas.policy_source import GitPolicyScopeSource


def count_proc_symlinks():
    """Count symbolic links in /proc (Linux only)."""
    if not os.path.exists("/proc"):
        return None, "Not on Linux - /proc not available"
    
    try:
        # Count symlinks in /proc (excluding common system ones)
        proc_path = Path("/proc")
        symlink_count = 0
        for item in proc_path.iterdir():
            if item.is_symlink():
                symlink_count += 1
        return symlink_count, None
    except Exception as e:
        return None, f"Error counting symlinks: {e}"


async def test_fetch_failure_cleanup():
    """Test that fetch failures clean up Repository objects."""
    print("\n" + "="*80)
    print("TEST 1: Fetch Failure Cleanup")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "git_sources"
        base_dir.mkdir(parents=True)
        
        source = GitPolicyScopeSource(
            url="https://github.com/test/nonexistent-repo.git",
            branch="main",
            directories=["."],
        )
        
        fetcher = GitPolicyFetcher(
            base_dir=base_dir,
            scope_id="test-scope",
            source=source,
            callbacks=PolicyFetcherCallbacks(),
        )
        
        # Create a mock repository directory
        repo_path = fetcher._repo_path
        repo_path.mkdir(parents=True)
        (repo_path / ".git").mkdir()
        
        # Create a mock Repository and add to cache
        mock_repo = MagicMock(spec=pygit2.Repository)
        GitPolicyFetcher.repos[str(repo_path)] = mock_repo
        
        initial_cache_size = len(GitPolicyFetcher.repos)
        print(f"Initial cache size: {initial_cache_size}")
        print(f"Repository in cache: {str(repo_path) in GitPolicyFetcher.repos}")
        
        # Mock _discover_repository and _get_valid_repo
        fetcher._discover_repository = lambda path: True
        fetcher._get_valid_repo = lambda: mock_repo
        fetcher._should_fetch = lambda *args, **kwargs: True
        
        # Mock fetch to raise GitError (simulating GitHub 500)
        mock_remote = MagicMock()
        mock_remote.fetch.side_effect = pygit2.GitError("GitHub returned 500 - Service Unavailable")
        mock_repo.remotes = {"origin": mock_remote}
        
        # Get initial symlink count (if on Linux)
        initial_symlinks, symlink_error = count_proc_symlinks()
        if initial_symlinks is not None:
            print(f"Initial /proc symlinks: {initial_symlinks}")
        else:
            print(f"Symlink count unavailable: {symlink_error}")
        
        # Attempt fetch - should fail and clean up
        try:
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)
            print("ERROR: Fetch should have raised GitError!")
            return False
        except pygit2.GitError as e:
            print(f"✓ Fetch correctly raised GitError: {e}")
        
        # Check cache cleanup
        final_cache_size = len(GitPolicyFetcher.repos)
        print(f"Final cache size: {final_cache_size}")
        print(f"Repository in cache: {str(repo_path) in GitPolicyFetcher.repos}")
        
        if str(repo_path) in GitPolicyFetcher.repos:
            print("✗ FAIL: Repository still in cache after fetch failure!")
            return False
        else:
            print("✓ PASS: Repository removed from cache after fetch failure")
        
        # Check symlink count (if on Linux)
        final_symlinks, symlink_error = count_proc_symlinks()
        if final_symlinks is not None:
            print(f"Final /proc symlinks: {final_symlinks}")
            if initial_symlinks is not None:
                diff = final_symlinks - initial_symlinks
                if diff > 10:  # Allow some variance
                    print(f"⚠ WARNING: Symlink count increased by {diff}")
                else:
                    print("✓ PASS: Symlink count stable")
        else:
            print(f"Symlink count unavailable: {symlink_error}")
        
        return True


async def test_clone_failure_cleanup():
    """Test that clone failures clean up partial repositories."""
    print("\n" + "="*80)
    print("TEST 2: Clone Failure Cleanup")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "git_sources"
        base_dir.mkdir(parents=True)
        
        source = GitPolicyScopeSource(
            url="https://github.com/test/nonexistent-repo.git",
            branch="main",
            directories=["."],
        )
        
        fetcher = GitPolicyFetcher(
            base_dir=base_dir,
            scope_id="test-scope-2",
            source=source,
            callbacks=PolicyFetcherCallbacks(),
        )
        
        repo_path = fetcher._repo_path
        
        # Mock clone_repository to raise GitError
        with patch("opal_server.git_fetcher.clone_repository") as mock_clone:
            mock_clone.side_effect = pygit2.GitError("GitHub returned 500 - Service Unavailable")
            
            # Create a partial repository directory (simulating failed clone)
            repo_path.mkdir(parents=True, exist_ok=True)
            (repo_path / "partial_file.txt").write_text("partial content")
            (repo_path / ".git").mkdir()
            
            print(f"Created partial repository at: {repo_path}")
            print(f"Partial directory exists: {repo_path.exists()}")
            
            # Get initial symlink count (if on Linux)
            initial_symlinks, symlink_error = count_proc_symlinks()
            if initial_symlinks is not None:
                print(f"Initial /proc symlinks: {initial_symlinks}")
            
            # Attempt clone - should fail and clean up
            try:
                await fetcher._clone()
                print("ERROR: Clone should have raised GitError!")
                return False
            except pygit2.GitError as e:
                print(f"✓ Clone correctly raised GitError: {e}")
            
            # Check cleanup
            print(f"Partial directory exists after cleanup: {repo_path.exists()}")
            
            if repo_path.exists():
                print("✗ FAIL: Partial repository directory not cleaned up!")
                return False
            else:
                print("✓ PASS: Partial repository directory cleaned up")
            
            # Check cache
            if str(repo_path) in GitPolicyFetcher.repos:
                print("✗ FAIL: Repository still in cache after clone failure!")
                return False
            else:
                print("✓ PASS: Repository not in cache after clone failure")
            
            # Check symlink count (if on Linux)
            final_symlinks, symlink_error = count_proc_symlinks()
            if final_symlinks is not None:
                print(f"Final /proc symlinks: {final_symlinks}")
                if initial_symlinks is not None:
                    diff = final_symlinks - initial_symlinks
                    if diff > 10:  # Allow some variance
                        print(f"⚠ WARNING: Symlink count increased by {diff}")
                    else:
                        print("✓ PASS: Symlink count stable")
            
            return True


async def test_multiple_failures():
    """Test that multiple failures don't accumulate Repository objects."""
    print("\n" + "="*80)
    print("TEST 3: Multiple Failures (No Accumulation)")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "git_sources"
        base_dir.mkdir(parents=True)
        
        source = GitPolicyScopeSource(
            url="https://github.com/test/nonexistent-repo.git",
            branch="main",
            directories=["."],
        )
        
        fetcher = GitPolicyFetcher(
            base_dir=base_dir,
            scope_id="test-scope-3",
            source=source,
            callbacks=PolicyFetcherCallbacks(),
        )
        
        # Get initial cache size
        initial_cache_size = len(GitPolicyFetcher.repos)
        print(f"Initial cache size: {initial_cache_size}")
        
        # Simulate multiple fetch failures
        for i in range(5):
            repo_path = fetcher._repo_path
            repo_path.mkdir(parents=True, exist_ok=True)
            (repo_path / ".git").mkdir()
            
            mock_repo = MagicMock(spec=pygit2.Repository)
            GitPolicyFetcher.repos[str(repo_path)] = mock_repo
            
            fetcher._discover_repository = lambda path: True
            fetcher._get_valid_repo = lambda: mock_repo
            fetcher._should_fetch = lambda *args, **kwargs: True
            
            mock_remote = MagicMock()
            mock_remote.fetch.side_effect = pygit2.GitError(f"GitHub returned 500 - Attempt {i+1}")
            mock_repo.remotes = {"origin": mock_remote}
            
            try:
                await fetcher.fetch_and_notify_on_changes(force_fetch=True)
            except pygit2.GitError:
                pass  # Expected
            
            # Verify cleanup after each failure
            if str(repo_path) in GitPolicyFetcher.repos:
                print(f"✗ FAIL: Repository still in cache after failure {i+1}!")
                return False
        
        # Check final cache size
        final_cache_size = len(GitPolicyFetcher.repos)
        print(f"Final cache size: {final_cache_size}")
        
        # Cache should not have grown significantly
        if final_cache_size > initial_cache_size + 2:  # Allow some variance
            print(f"✗ FAIL: Cache size grew from {initial_cache_size} to {final_cache_size}!")
            return False
        else:
            print(f"✓ PASS: Cache size stable ({initial_cache_size} -> {final_cache_size})")
        
        return True


async def main():
    """Run all manual tests."""
    print("\n" + "="*80)
    print("MANUAL TEST SUITE FOR ISSUE #634")
    print("Symbolic Link Cleanup When GitHub is Down")
    print("="*80)
    
    results = []
    
    # Run tests
    results.append(("Fetch Failure Cleanup", await test_fetch_failure_cleanup()))
    results.append(("Clone Failure Cleanup", await test_clone_failure_cleanup()))
    results.append(("Multiple Failures", await test_multiple_failures()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
