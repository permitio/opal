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

from pathlib import Path

from git import Repo
from git.objects.commit import Commit
from opal_common.git.branch_tracker import BranchTracker
from opal_common.git.exceptions import GitFailed


def test_pull_with_no_changes(local_repo_clone: Repo):
    """Test pulling when there are no changes on the remote repo."""
    repo: Repo = local_repo_clone  # local repo, cloned from another local repo

    tracker = BranchTracker(repo=repo)
    latest_commit: Commit = repo.head.commit
    assert latest_commit == tracker.latest_commit == tracker.prev_commit
    has_changes, prev, latest = tracker.pull()  # pulls from origin
    assert has_changes == False
    assert latest_commit == prev == latest


def test_pull_with_new_commits(
    local_repo: Repo,
    local_repo_clone: Repo,
    helpers,
):
    """Test pulling when there are changes (new commits) on the remote repo."""
    remote_repo: Repo = (
        local_repo  # local repo, the 'origin' remote of 'local_repo_clone'
    )
    repo: Repo = local_repo_clone  # local repo, cloned from 'local_repo'

    tracker = BranchTracker(repo=repo)
    most_recent_commit_before_pull: Commit = repo.head.commit

    assert (
        most_recent_commit_before_pull == tracker.latest_commit == tracker.prev_commit
    )

    # create new file commit on the remote repo
    helpers.create_new_file_commit(
        remote_repo, Path(remote_repo.working_tree_dir) / "2.txt"
    )

    # now the remote repo head is different
    assert remote_repo.head.commit != repo.head.commit
    # and our branch tracker does not know it yet
    assert remote_repo.head.commit != tracker.latest_commit

    has_changes, prev, latest = tracker.pull()  # pulls from origin
    assert has_changes == True
    assert prev != latest
    assert most_recent_commit_before_pull == prev
    assert (
        remote_repo.head.commit == repo.head.commit == latest == tracker.latest_commit
    )


def test_tracked_branch_does_not_exist(local_repo: Repo):
    """Test that branch tracker throws when branch does not exist."""
    with pytest.raises(GitFailed):
        tracker = BranchTracker(local_repo, branch_name="no_such_branch")


def test_tracked_remote_does_not_exist(local_repo_clone: Repo):
    """Test that branch tracker throws when remote does not exist."""
    tracker = BranchTracker(local_repo_clone, remote_name="not_a_remote")
    with pytest.raises(GitFailed):
        remote = tracker.tracked_remote
    with pytest.raises(GitFailed):
        tracker.pull()
