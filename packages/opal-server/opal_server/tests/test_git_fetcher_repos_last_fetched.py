import datetime
from pathlib import Path

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server.git_fetcher import GitPolicyFetcher


def _make_fetcher(
    base_dir: Path, scope_id: str, url: str, branch: str = "main"
) -> GitPolicyFetcher:
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch=branch,
        auth=NoAuthData(auth_type="none"),
    )
    return GitPolicyFetcher(
        base_dir=base_dir,
        scope_id=scope_id,
        source=source,
    )


@pytest.fixture(autouse=True)
def _reset_class_state():
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    GitPolicyFetcher.repos.clear()
    yield
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    GitPolicyFetcher.repos.clear()


@pytest.mark.asyncio
async def test_was_fetched_after_is_per_source(tmp_path):
    """A recent fetch on source X must not cause source Y's refresh to be
    skipped."""
    fetcher_x = _make_fetcher(tmp_path, "scope_x", "https://example.com/repo-x.git")
    fetcher_y = _make_fetcher(tmp_path, "scope_y", "https://example.com/repo-y.git")

    now = datetime.datetime.now()
    GitPolicyFetcher.repos_last_fetched[
        fetcher_x._source_id
    ] = now + datetime.timedelta(seconds=1)

    assert await fetcher_x._was_fetched_after(now) is True
    assert await fetcher_y._was_fetched_after(now) is False


@pytest.mark.asyncio
async def test_repos_last_fetched_keyed_by_source_string(tmp_path):
    """Keys in repos_last_fetched must be the per-source hash string, not a
    function object."""
    fetcher = _make_fetcher(tmp_path, "scope_x", "https://example.com/repo-x.git")
    expected_key = GitPolicyFetcher.source_id(fetcher._source)

    assert fetcher._source_id == expected_key
    assert isinstance(fetcher._source_id, str)

    GitPolicyFetcher.repos_last_fetched[expected_key] = datetime.datetime.now()

    assert expected_key in GitPolicyFetcher.repos_last_fetched
    assert isinstance(expected_key, str)
    assert all(isinstance(k, str) for k in GitPolicyFetcher.repos_last_fetched)
    assert GitPolicyFetcher.source_id not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_force_fetch_not_downgraded_by_sibling_source(monkeypatch, tmp_path):
    fetcher_x = _make_fetcher(tmp_path, "scope_x", "https://example.com/repo-x.git")
    fetcher_y = _make_fetcher(tmp_path, "scope_y", "https://example.com/repo-y.git")

    req_time = datetime.datetime.now()
    GitPolicyFetcher.repos_last_fetched[
        fetcher_x._source_id
    ] = req_time + datetime.timedelta(seconds=1)

    monkeypatch.setattr(
        "opal_server.git_fetcher.RepoInterface.has_remote_branch",
        lambda repo, branch, remote: True,
    )

    assert (
        await fetcher_y._should_fetch(
            repo=object(), force_fetch=True, req_time=req_time
        )
        is True
    )
