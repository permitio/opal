import os
import sys

import pytest

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)

import asyncio
from functools import partial
from pathlib import Path
from typing import Dict, Optional

from git import Repo
from git.objects import Commit
from opal_common.sources.git_policy_source import GitPolicySource

try:
    from asyncio.exceptions import TimeoutError
except ImportError:
    from asyncio import TimeoutError

VALID_REPO_REMOTE_URL_HTTPS = "https://github.com/permitio/fastapi_websocket_pubsub.git"

INVALID_REPO_REMOTE_URL = "git@github.com:permitio/no_such_repo.git"


@pytest.mark.asyncio
async def test_repo_watcher_git_failed_callback(tmp_path):
    """checks that on failure to clone, the failure callback is called."""
    got_error = asyncio.Event()

    async def failure_callback(e: Exception):
        got_error.set()

    target_path: Path = tmp_path / "target"

    # configure the watcher to watch an invalid repo
    watcher = GitPolicySource(
        remote_source_url=INVALID_REPO_REMOTE_URL,
        local_clone_path=target_path,
        request_timeout=3,
    )
    # configure the error callback
    watcher.add_on_failure_callback(failure_callback)

    # run the watcher
    await watcher.run()

    # assert the error callback is called
    await asyncio.wait_for(got_error.wait(), 25)
    assert got_error.is_set()


@pytest.mark.asyncio
async def test_repo_watcher_detect_new_commits_with_manual_trigger(
    local_repo: Repo,
    tmp_path,
    helpers,
):
    """Test watcher can detect new commits on a manual trigger to check for
    changes, and it calls the add_on_new_policy_callback() callback."""
    # start with preconfigured repos
    remote_repo: Repo = local_repo  # the 'origin' repo (also a local test repo)

    detected_new_commits = asyncio.Event()
    detected_commits: Dict[str, Optional[Commit]] = dict(old=None, new=None)

    async def new_commits_callback(
        commits: Dict[str, Optional[Commit]], old: Commit, new: Commit
    ):
        commits["old"] = old
        commits["new"] = new
        detected_new_commits.set()

    target_path: Path = tmp_path / "target_manual_trigger"

    # configure the watcher with a valid local repo (our test repo)
    # the returned repo will track the local remote repo
    watcher = GitPolicySource(
        remote_source_url=remote_repo.working_tree_dir, local_clone_path=target_path
    )
    # configure the error callback
    watcher.add_on_new_policy_callback(partial(new_commits_callback, detected_commits))

    # run the watcher (without polling)
    await watcher.run()

    # assert watcher will not detect new commits when forced to check
    await watcher.check_for_changes()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(detected_new_commits.wait(), 5)
    assert not detected_new_commits.is_set()
    assert detected_commits["old"] is None
    assert detected_commits["new"] is None

    # make sure tracked repo and remote repo have the same head
    repo: Repo = watcher._tracker.repo
    assert repo.head.commit == remote_repo.head.commit

    prev_head: Commit = repo.head.commit

    # create new file commit on the remote repo
    helpers.create_new_file_commit(
        remote_repo, Path(remote_repo.working_tree_dir) / "2.txt"
    )
    # now the remote repo head is different
    assert remote_repo.head.commit != repo.head.commit

    new_expected_head: Commit = remote_repo.head.commit

    # assert watcher *will* detect the new commits when forced to check
    await watcher.check_for_changes()
    await asyncio.wait_for(detected_new_commits.wait(), 5)
    assert detected_new_commits.is_set()
    # assert the expected commits are detected and passed to the callback
    assert detected_commits["old"] == prev_head
    assert detected_commits["new"] == new_expected_head

    # assert local repo was updated and again matches the state of remote repo
    assert repo.head.commit == remote_repo.head.commit == new_expected_head


@pytest.mark.asyncio
async def test_repo_watcher_detect_new_commits_with_polling(
    local_repo: Repo,
    tmp_path,
    helpers,
):
    """Test watcher can detect new commits on a manual trigger to check for
    changes, and it calls the add_on_new_policy_callback() callback."""
    # start with preconfigured repos
    remote_repo: Repo = local_repo  # the 'origin' repo (also a local test repo)

    detected_new_commits = asyncio.Event()
    detected_commits: Dict[str, Optional[Commit]] = dict(old=None, new=None)

    async def new_commits_callback(
        commits: Dict[str, Optional[Commit]], old: Commit, new: Commit
    ):
        commits["old"] = old
        commits["new"] = new
        detected_new_commits.set()

    target_path: Path = tmp_path / "target_polling"

    # configure the watcher with a valid local repo (our test repo)
    # the returned repo will track the test remote, not a real remote
    watcher = GitPolicySource(
        remote_source_url=remote_repo.working_tree_dir,
        local_clone_path=target_path,
        polling_interval=3,  # every 3 seconds do a pull to try and detect changes
    )
    # configure the error callback
    watcher.add_on_new_policy_callback(partial(new_commits_callback, detected_commits))

    # run the watcher (without polling)
    await watcher.run()

    # assert watcher will not detect new commits after 6 seconds (enough for first polling check)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(detected_new_commits.wait(), 6)
    assert not detected_new_commits.is_set()
    assert detected_commits["old"] is None
    assert detected_commits["new"] is None

    # make sure tracked repo and remote repo have the same head
    repo: Repo = watcher._tracker.repo
    assert repo.head.commit == remote_repo.head.commit

    prev_head: Commit = repo.head.commit

    # create new file commit on the remote repo
    helpers.create_new_file_commit(
        remote_repo, Path(remote_repo.working_tree_dir) / "2.txt"
    )
    # now the remote repo head is different
    assert remote_repo.head.commit != repo.head.commit

    new_expected_head: Commit = remote_repo.head.commit

    # assert watcher *will* detect the new commits with a few more seconds to wait
    await asyncio.wait_for(detected_new_commits.wait(), 6)
    assert detected_new_commits.is_set()
    # assert the expected commits are detected and passed to the callback
    assert detected_commits["old"] == prev_head
    assert detected_commits["new"] == new_expected_head

    # assert local repo was updated and again matches the state of remote repo
    assert repo.head.commit == remote_repo.head.commit == new_expected_head

    # stops the watcher outstanding tasks
    await watcher.stop()
