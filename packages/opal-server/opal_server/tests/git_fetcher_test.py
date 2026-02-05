import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks


def _make_source(url="https://example.com/repo.git", branch="main"):
    """Create a minimal GitPolicyScopeSource for testing."""
    return GitPolicyScopeSource(
        source_type="GIT",
        url=url,
        branch=branch,
        auth=NoAuthData(),
        directories=["."],
        extensions=[".rego", ".json"],
        manifest=".manifest",
        bundle_ignore=None,
    )


def _make_fetcher(source=None, clone_timeout=0, callbacks=None):
    """Create a GitPolicyFetcher with mocked paths and config."""
    if source is None:
        source = _make_source()
    if callbacks is None:
        callbacks = PolicyFetcherCallbacks()
    return GitPolicyFetcher(
        base_dir=Path("/tmp/test_opal"),
        scope_id="test-scope",
        source=source,
        callbacks=callbacks,
        clone_timeout=clone_timeout,
    )


@pytest.fixture(autouse=True)
def _clear_class_state():
    """Clear GitPolicyFetcher class-level caches between tests."""
    GitPolicyFetcher.repo_locks.clear()
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    yield
    GitPolicyFetcher.repo_locks.clear()
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()


# ---------------------------------------------------------------------------
# Clone tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("opal_server.git_fetcher.GitCallback")
@patch("opal_server.git_fetcher.clone_repository")
async def test_clone_timeout_raises_on_slow_operation(mock_clone, mock_git_cb):
    """When clone_repository blocks longer than the timeout, asyncio.TimeoutError propagates."""

    def slow_clone(*args, **kwargs):
        time.sleep(10)

    mock_clone.side_effect = slow_clone
    mock_git_cb.return_value = MagicMock()

    fetcher = _make_fetcher(clone_timeout=0.5)

    with pytest.raises(asyncio.TimeoutError):
        await fetcher._clone()


@pytest.mark.asyncio
@patch("opal_server.git_fetcher.GitCallback")
@patch("opal_server.git_fetcher.clone_repository")
async def test_clone_reraises_git_error(mock_clone, mock_git_cb):
    """pygit2.GitError from clone_repository must NOT be swallowed; it should propagate."""
    mock_clone.side_effect = pygit2.GitError("auth failed")
    mock_git_cb.return_value = MagicMock()

    fetcher = _make_fetcher()

    with pytest.raises(pygit2.GitError, match="auth failed"):
        await fetcher._clone()


@pytest.mark.asyncio
@patch("opal_server.git_fetcher.GitCallback")
@patch("opal_server.git_fetcher.clone_repository")
async def test_clone_success(mock_clone, mock_git_cb):
    """A successful clone should call _notify_on_changes."""
    mock_repo = MagicMock()
    mock_clone.return_value = mock_repo
    mock_git_cb.return_value = MagicMock()

    fetcher = _make_fetcher()
    fetcher._notify_on_changes = AsyncMock()

    await fetcher._clone()

    mock_clone.assert_called_once()
    fetcher._notify_on_changes.assert_awaited_once_with(mock_repo)


@pytest.mark.asyncio
@patch("opal_server.git_fetcher.GitCallback")
@patch("opal_server.git_fetcher.clone_repository")
async def test_clone_no_timeout_when_zero(mock_clone, mock_git_cb):
    """When clone_timeout=0, no asyncio.wait_for timeout is applied.

    We verify this by having a function that takes a short time but would fail
    with a zero-second timeout if one were mistakenly applied.
    """

    def quick_clone(*args, **kwargs):
        time.sleep(0.1)
        return MagicMock()

    mock_clone.side_effect = quick_clone
    mock_git_cb.return_value = MagicMock()

    fetcher = _make_fetcher(clone_timeout=0)
    fetcher._notify_on_changes = AsyncMock()

    # Should complete without TimeoutError
    await fetcher._clone()
    mock_clone.assert_called_once()


# ---------------------------------------------------------------------------
# Fetch tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("opal_server.git_fetcher.GitCallback")
@patch("opal_server.git_fetcher.discover_repository", return_value=True)
async def test_fetch_timeout_raises_on_slow_operation(mock_discover, mock_git_cb):
    """When the fetch operation blocks longer than the timeout, asyncio.TimeoutError propagates."""
    mock_git_cb.return_value = MagicMock()

    source = _make_source()
    fetcher = _make_fetcher(source=source, clone_timeout=0.5)

    # Set up a mock repo with a slow fetch
    mock_remote = MagicMock()

    def slow_fetch(**kwargs):
        time.sleep(10)

    mock_remote.fetch = slow_fetch

    mock_repo = MagicMock()
    mock_repo.remotes = {"origin": mock_remote}

    # Patch _discover_repository and _get_valid_repo to enter the fetch path
    fetcher._discover_repository = MagicMock(return_value=True)
    fetcher._get_valid_repo = MagicMock(return_value=mock_repo)
    fetcher._should_fetch = AsyncMock(return_value=True)
    fetcher._notify_on_changes = AsyncMock()

    with pytest.raises(asyncio.TimeoutError):
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)
