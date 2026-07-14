import datetime
from pathlib import Path

import pygit2
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


class _FailingRemote:
    def fetch(self, *args, **kwargs):
        raise pygit2.GitError("network down")


class _OkRemote:
    def fetch(self, *args, **kwargs):
        return None


class _FakeRepo:
    def __init__(self, remote):
        self.remotes = {"origin": remote}


@pytest.mark.asyncio
async def test_failed_fetch_does_not_stamp_last_fetched(monkeypatch, tmp_path):
    """Bug B: stamping before the fetch means a FAILED fetch still records
    "fetched now", which suppresses the next webhook-requested forced refresh
    via _was_fetched_after()."""
    fetcher = _make_fetcher(tmp_path, "scope_x", "https://example.com/repo-x.git")
    monkeypatch.setattr(fetcher, "_discover_repository", lambda path: True)
    monkeypatch.setattr(fetcher, "_get_valid_repo", lambda: _FakeRepo(_FailingRemote()))

    with pytest.raises(pygit2.GitError):
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetcher._source_id not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_successful_fetch_stamps_last_fetched(monkeypatch, tmp_path):
    fetcher = _make_fetcher(tmp_path, "scope_x", "https://example.com/repo-x.git")
    monkeypatch.setattr(fetcher, "_discover_repository", lambda path: True)
    monkeypatch.setattr(fetcher, "_get_valid_repo", lambda: _FakeRepo(_OkRemote()))

    async def _no_notify(repo):
        return None

    monkeypatch.setattr(fetcher, "_notify_on_changes", _no_notify)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetcher._source_id in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_stamp_records_fetch_start_time_not_completion(monkeypatch, tmp_path):
    """The stamp must be the fetch START time: a fetch that STARTED after a
    refresh's req_time already satisfies it; completion time would wrongly
    suppress refreshes requested mid-fetch."""
    import time as _time

    class _SlowRemote:
        def __init__(self):
            self.entered_at = None

        def fetch(self, *args, **kwargs):
            self.entered_at = datetime.datetime.now()
            _time.sleep(0.05)

    remote = _SlowRemote()
    fetcher = _make_fetcher(tmp_path, "scope_x", "https://example.com/repo-x.git")
    monkeypatch.setattr(fetcher, "_discover_repository", lambda path: True)
    monkeypatch.setattr(fetcher, "_get_valid_repo", lambda: _FakeRepo(remote))

    async def _no_notify(repo):
        return None

    monkeypatch.setattr(fetcher, "_notify_on_changes", _no_notify)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    stamp = GitPolicyFetcher.repos_last_fetched[fetcher._source_id]
    assert stamp <= remote.entered_at, (
        "stamp is later than the fetch's entry time — completion time was "
        "stored instead of start time"
    )
