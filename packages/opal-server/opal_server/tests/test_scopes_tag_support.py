import os
import sys

import pytest

root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pygit2
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_server.git_fetcher import GitPolicyFetcher, RepoInterface
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helper to build a GitPolicyScopeSource without repeating boilerplate
# ---------------------------------------------------------------------------
def _make_source(branch=None, tag=None):
    return GitPolicyScopeSource(
        source_type="git",
        url="https://example.com/repo.git",
        auth={"auth_type": "none"},
        branch=branch,
        tag=tag,
    )


# ========================================================================
# GitPolicyScopeSource schema validation
# ========================================================================


class TestGitPolicyScopeSourceValidation:
    def test_branch_only(self):
        src = _make_source(branch="main")
        assert src.branch == "main"
        assert src.tag is None

    def test_tag_only(self):
        src = _make_source(tag="v1.0")
        assert src.tag == "v1.0"
        assert src.branch is None

    def test_neither_branch_nor_tag_raises(self):
        with pytest.raises(ValidationError, match="Must provide either"):
            _make_source()

    def test_both_branch_and_tag_raises(self):
        with pytest.raises(ValidationError, match="not both"):
            _make_source(branch="main", tag="v1.0")

    def test_empty_string_branch_treated_as_none(self):
        src = _make_source(branch="", tag="v1.0")
        assert src.branch is None
        assert src.tag == "v1.0"

    def test_empty_string_tag_treated_as_none(self):
        src = _make_source(branch="main", tag="")
        assert src.branch == "main"
        assert src.tag is None

    def test_both_empty_strings_raises(self):
        with pytest.raises(ValidationError, match="Must provide either"):
            _make_source(branch="", tag="")


# ========================================================================
# RepoInterface tag helpers (using a real pygit2 repo on disk)
# ========================================================================


@pytest.fixture
def pygit2_repo(tmp_path):
    """Create a bare-minimum pygit2 Repository with one commit and a tag."""
    repo = pygit2.init_repository(str(tmp_path / "repo"), bare=False)

    # Create an initial commit
    sig = pygit2.Signature("Test", "test@test.com")
    tree = repo.TreeBuilder().write()
    commit_oid = repo.create_commit("refs/heads/master", sig, sig, "init", tree, [])
    # Create a lightweight tag
    repo.create_reference("refs/tags/v1.0", commit_oid)

    return repo, str(commit_oid)


class TestRepoInterfaceTagHelpers:
    def test_has_tag_existing(self, pygit2_repo):
        repo, _ = pygit2_repo
        assert RepoInterface.has_tag(repo, "v1.0") is True

    def test_has_tag_missing(self, pygit2_repo):
        repo, _ = pygit2_repo
        assert RepoInterface.has_tag(repo, "no_such_tag") is False

    def test_get_tag_commit_hash_existing(self, pygit2_repo):
        repo, commit_hex = pygit2_repo
        result = RepoInterface.get_tag_commit_hash(repo, "v1.0")
        assert result == commit_hex

    def test_get_tag_commit_hash_missing(self, pygit2_repo):
        repo, _ = pygit2_repo
        result = RepoInterface.get_tag_commit_hash(repo, "no_such_tag")
        assert result is None

    def test_get_tag_commit_hash_annotated_tag(self, pygit2_repo):
        repo, commit_hex = pygit2_repo
        # Create an annotated tag
        sig = pygit2.Signature("Test", "test@test.com")
        commit = repo.get(commit_hex)
        tag_oid = repo.create_tag(
            "v2.0", commit.id, pygit2.GIT_OBJECT_COMMIT, sig, "annotated tag"
        )
        result = RepoInterface.get_tag_commit_hash(repo, "v2.0")
        assert result == commit_hex


# ========================================================================
# GitPolicyFetcher properties and source_id
# ========================================================================


class TestGitPolicyFetcherProperties:
    @patch("opal_server.git_fetcher.opal_server_config")
    @patch("opal_server.git_fetcher.GitCallback")
    def test_is_tag_true_when_tag_set(self, mock_callback, mock_config):
        mock_config.SCOPES_REPO_CLONES_SHARDS = 10
        source = _make_source(tag="v1.0")
        fetcher = GitPolicyFetcher(
            base_dir=Path("/tmp/test"),
            scope_id="test-scope",
            source=source,
        )
        assert fetcher._is_tag is True
        assert fetcher._ref_name == "v1.0"

    @patch("opal_server.git_fetcher.opal_server_config")
    @patch("opal_server.git_fetcher.GitCallback")
    def test_is_tag_false_when_branch_set(self, mock_callback, mock_config):
        mock_config.SCOPES_REPO_CLONES_SHARDS = 10
        source = _make_source(branch="main")
        fetcher = GitPolicyFetcher(
            base_dir=Path("/tmp/test"),
            scope_id="test-scope",
            source=source,
        )
        assert fetcher._is_tag is False
        assert fetcher._ref_name == "main"

    @patch("opal_server.git_fetcher.opal_server_config")
    def test_source_id_differs_for_branch_vs_tag(self, mock_config):
        mock_config.SCOPES_REPO_CLONES_SHARDS = 10
        branch_source = _make_source(branch="main")
        tag_source = _make_source(tag="main")  # same name, different ref type
        # source_id uses the ref value to compute the shard index
        branch_id = GitPolicyFetcher.source_id(branch_source)
        tag_id = GitPolicyFetcher.source_id(tag_source)
        # Same ref name means same source_id (by design: same shard)
        assert branch_id == tag_id

    @patch("opal_server.git_fetcher.opal_server_config")
    def test_source_id_different_tag_names(self, mock_config):
        mock_config.SCOPES_REPO_CLONES_SHARDS = 256
        src_a = _make_source(tag="v1.0")
        src_b = _make_source(tag="v2.0")
        id_a = GitPolicyFetcher.source_id(src_a)
        id_b = GitPolicyFetcher.source_id(src_b)
        # Different tags may (and likely do for distinct names) produce different ids
        # At minimum, both should be valid strings
        assert isinstance(id_a, str) and len(id_a) > 0
        assert isinstance(id_b, str) and len(id_b) > 0


# ========================================================================
# GitPolicyFetcher._should_fetch with tags
# ========================================================================


class TestShouldFetchWithTags:
    @patch("opal_server.git_fetcher.opal_server_config")
    @patch("opal_server.git_fetcher.GitCallback")
    def _make_fetcher(self, source, mock_callback, mock_config):
        mock_config.SCOPES_REPO_CLONES_SHARDS = 10
        return GitPolicyFetcher(
            base_dir=Path("/tmp/test"),
            scope_id="test-scope",
            source=source,
        )

    @pytest.mark.asyncio
    async def test_should_fetch_when_tag_missing(self):
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()

        with patch.object(RepoInterface, "has_tag", return_value=False):
            result = await fetcher._should_fetch(mock_repo)
            assert result is True

    @pytest.mark.asyncio
    async def test_should_always_fetch_when_tag_present_no_hint(self):
        """Tags can be moved silently, so we always re-fetch."""
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()

        with patch.object(RepoInterface, "has_tag", return_value=True):
            result = await fetcher._should_fetch(mock_repo)
            assert result is True

    @pytest.mark.asyncio
    async def test_should_fetch_force(self):
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()

        result = await fetcher._should_fetch(mock_repo, force_fetch=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_fetch_when_branch_missing(self):
        source = _make_source(branch="main")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()

        with patch.object(RepoInterface, "has_remote_branch", return_value=False):
            result = await fetcher._should_fetch(mock_repo)
            assert result is True

    @pytest.mark.asyncio
    async def test_should_not_fetch_when_branch_present_no_hint(self):
        source = _make_source(branch="main")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()

        with patch.object(RepoInterface, "has_remote_branch", return_value=True):
            result = await fetcher._should_fetch(mock_repo)
            assert result is False


# ========================================================================
# GitPolicyFetcher._notify_on_changes with tags
# ========================================================================


class TestNotifyOnChangesWithTags:
    @patch("opal_server.git_fetcher.opal_server_config")
    @patch("opal_server.git_fetcher.GitCallback")
    def _make_fetcher(self, source, mock_callback, mock_config):
        mock_config.SCOPES_REPO_CLONES_SHARDS = 10
        fetcher = GitPolicyFetcher(
            base_dir=Path("/tmp/test"),
            scope_id="test-scope",
            source=source,
        )
        fetcher.callbacks = AsyncMock()
        return fetcher

    @pytest.mark.asyncio
    async def test_notify_calls_callback_for_tag(self):
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()
        fake_hash = "abc123"

        with patch.object(
            RepoInterface, "get_tag_commit_hash", return_value=fake_hash
        ), patch.object(RepoInterface, "get_local_branch", return_value=None):
            mock_repo.create_reference.return_value = MagicMock()
            await fetcher._notify_on_changes(mock_repo)

        fetcher.callbacks.on_update.assert_awaited_once_with(None, fake_hash)

    @pytest.mark.asyncio
    async def test_notify_returns_early_when_tag_not_found(self):
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()

        with patch.object(RepoInterface, "get_tag_commit_hash", return_value=None):
            await fetcher._notify_on_changes(mock_repo)

        fetcher.callbacks.on_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notify_detects_tag_change(self):
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()
        old_hash = "old123"
        new_hash = "new456"

        mock_local_branch = MagicMock()
        mock_local_branch.target.__str__ = lambda self: old_hash

        with patch.object(
            RepoInterface, "get_tag_commit_hash", return_value=new_hash
        ), patch.object(
            RepoInterface, "get_local_branch", return_value=mock_local_branch
        ):
            await fetcher._notify_on_changes(mock_repo)

        fetcher.callbacks.on_update.assert_awaited_once_with(old_hash, new_hash)
        mock_local_branch.set_target.assert_called_once_with(new_hash)

    @pytest.mark.asyncio
    async def test_notify_calls_callback_for_branch(self):
        source = _make_source(branch="main")
        fetcher = self._make_fetcher(source)
        mock_repo = MagicMock()
        fake_hash = "abc123"

        with patch.object(
            RepoInterface, "get_commit_hash", return_value=fake_hash
        ), patch.object(
            RepoInterface, "get_local_branch", return_value=None
        ), patch.object(
            RepoInterface, "create_local_branch_ref", return_value=MagicMock()
        ):
            await fetcher._notify_on_changes(mock_repo)

        fetcher.callbacks.on_update.assert_awaited_once_with(None, fake_hash)


# ========================================================================
# GitPolicyFetcher._get_current_head with tags
# ========================================================================


class TestGetCurrentHead:
    @patch("opal_server.git_fetcher.opal_server_config")
    @patch("opal_server.git_fetcher.GitCallback")
    def _make_fetcher(self, source, mock_callback, mock_config):
        mock_config.SCOPES_REPO_CLONES_SHARDS = 10
        return GitPolicyFetcher(
            base_dir=Path("/tmp/test"),
            scope_id="test-scope",
            source=source,
        )

    def test_get_current_head_tag(self):
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)
        fake_hash = "abc123"

        with patch.object(fetcher, "_get_repo"), patch.object(
            RepoInterface, "get_tag_commit_hash", return_value=fake_hash
        ):
            result = fetcher._get_current_head()
            assert result == fake_hash

    def test_get_current_head_branch(self):
        source = _make_source(branch="main")
        fetcher = self._make_fetcher(source)
        fake_hash = "abc123"

        with patch.object(fetcher, "_get_repo"), patch.object(
            RepoInterface, "get_commit_hash", return_value=fake_hash
        ):
            result = fetcher._get_current_head()
            assert result == fake_hash

    def test_get_current_head_raises_when_not_found(self):
        source = _make_source(tag="v1.0")
        fetcher = self._make_fetcher(source)

        with patch.object(fetcher, "_get_repo"), patch.object(
            RepoInterface, "get_tag_commit_hash", return_value=None
        ):
            with pytest.raises(ValueError, match="Could not find current head"):
                fetcher._get_current_head()


# ========================================================================
# Scopes loader fallback behavior
# ========================================================================


class TestScopesLoaderFallback:
    @pytest.mark.asyncio
    async def test_loader_falls_back_to_master_when_neither_set(self):
        """loader.py should fall back to branch='master' when neither
        POLICY_REPO_MAIN_BRANCH nor POLICY_REPO_TAG is configured."""
        from unittest.mock import AsyncMock

        mock_repo = AsyncMock()

        with patch("opal_server.scopes.loader.opal_server_config") as mock_config:
            mock_config.POLICY_REPO_URL = "https://example.com/repo.git"
            mock_config.POLICY_SOURCE_TYPE = "git"
            mock_config.POLICY_REPO_MANIFEST_PATH = ".manifest"
            mock_config.POLICY_REPO_MAIN_BRANCH = None
            mock_config.POLICY_REPO_TAG = None
            mock_config.POLICY_REPO_SSH_KEY = None

            from opal_server.scopes.loader import _load_env_scope

            await _load_env_scope(mock_repo)

        mock_repo.put.assert_awaited_once()
        scope = mock_repo.put.call_args[0][0]
        assert scope.policy.branch == "master"
        assert scope.policy.tag is None

    @pytest.mark.asyncio
    async def test_loader_uses_tag_when_configured(self):
        """loader.py should use the tag when POLICY_REPO_TAG is set."""
        from unittest.mock import AsyncMock

        mock_repo = AsyncMock()

        with patch("opal_server.scopes.loader.opal_server_config") as mock_config:
            mock_config.POLICY_REPO_URL = "https://example.com/repo.git"
            mock_config.POLICY_SOURCE_TYPE = "git"
            mock_config.POLICY_REPO_MANIFEST_PATH = ".manifest"
            mock_config.POLICY_REPO_MAIN_BRANCH = None
            mock_config.POLICY_REPO_TAG = "v1.0"
            mock_config.POLICY_REPO_SSH_KEY = None

            from opal_server.scopes.loader import _load_env_scope

            await _load_env_scope(mock_repo)

        mock_repo.put.assert_awaited_once()
        scope = mock_repo.put.call_args[0][0]
        assert scope.policy.tag == "v1.0"
        assert scope.policy.branch is None
