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
from opal_common.git.tag_tracker import TagTracker
from opal_common.git.exceptions import GitFailed


def test_pull_with_no_changes(local_repo_clone: Repo):
    """Test pulling when there are no changes on the remote repo."""
    repo: Repo = local_repo_clone  # local repo, cloned from another local repo
    tracker = TagTracker(repo=repo, tag_name="test_tag")
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

    tracker = TagTracker(repo=repo, tag_name="test_tag")
    most_recent_commit_before_pull: Commit = repo.head.commit

    assert (
        most_recent_commit_before_pull == tracker.latest_commit == tracker.prev_commit
    )

    # create new file commit on the remote repo
    helpers.create_new_file_commit(
        remote_repo, Path(remote_repo.working_tree_dir) / "2.txt"
    )

    helpers.update_tag_to_head(remote_repo, "test_tag")

    # now the remote repo tag is pointing at a different commit
    assert remote_repo.tags.__getattr__("test_tag").commit != repo.head.commit
    # and our tag tracker does not know it yet
    assert remote_repo.tags.__getattr__("test_tag").commit != tracker.latest_commit

    has_changes, prev, latest = tracker.pull()  # pulls from origin
    assert has_changes == True
    assert prev != latest
    assert most_recent_commit_before_pull == prev
    assert (
        remote_repo.tags.__getattr__("test_tag").commit == repo.tags.__getattr__("test_tag").commit == latest == tracker.latest_commit
    )


def test_tracked_branch_does_not_exist(local_repo: Repo):
    """Test that tag tracker throws when tag does not exist."""
    with pytest.raises(GitFailed):
        tracker = TagTracker(local_repo, tag_name="no_such_tag")
