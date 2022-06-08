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

from functools import partial
from pathlib import Path
from typing import List, Tuple

from git import Diff, Repo
from git.objects import Commit
from opal_common.git.commit_viewer import VersionedFile
from opal_common.git.diff_viewer import DiffViewer, diffed_file_is_under_directories


def diff_paths(diffs: List[Diff]) -> List[Path]:
    paths = set()
    for diff in diffs:
        for path in [diff.a_path, diff.b_path]:
            if path is not None:
                paths.add(Path(path))
    return list(paths)


def file_paths(files: List[VersionedFile]) -> List[Path]:
    return [file.path for file in files]


def test_diff_viewer_filter_changes(repo_with_diffs: Tuple[Repo, Commit, Commit]):
    """Test returning changes() only in a certain directory."""
    repo, previous_head, new_head = repo_with_diffs

    # now we can test what changes are returned
    with DiffViewer(previous_head, new_head) as viewer:
        diffs = list(viewer.changes())
        assert len(diffs) == 4  # we touched (made any type of change) to 4 files

        paths = diff_paths(diffs)
        assert Path("other/gbac.rego") in paths
        assert Path("mylist.txt") in paths
        assert Path("other/data.json") in paths
        # renamed file diffs have 2 paths (old and new)
        assert Path("ignored.json") in paths
        assert Path("ignored2.json") in paths

        # now lets apply a filter
        diffs = list(
            viewer.changes(
                partial(diffed_file_is_under_directories, directories={Path("other")})
            )
        )
        # only diffs under 'other' directory is returned
        # matching diffs:
        # (A) other/gbac.rego
        # (D) other/data.json
        assert len(diffs) == 2

        paths = diff_paths(diffs)
        assert Path("other/gbac.rego") in paths
        assert Path("other/data.json") in paths
        assert Path("mylist.txt") not in paths
        assert Path("ignored2.json") not in paths


def test_diff_viewer_filter_by_change_type(
    repo_with_diffs: Tuple[Repo, Commit, Commit]
):
    """Test added(), deleted(), renamed(), modified() return only appropriate
    diffs."""
    repo, previous_head, new_head = repo_with_diffs
    with DiffViewer(previous_head, new_head) as viewer:
        # we added 1 file, we expect the added() generator to return only 1 diff
        diffs = list(viewer.added())
        assert len(diffs) == 1
        paths = diff_paths(diffs)
        assert Path("other/gbac.rego") in paths

        # we modified 1 file, we expect the modified() generator to return only 1 diff
        diffs = list(viewer.modified())
        assert len(diffs) == 1
        paths = diff_paths(diffs)
        assert Path("mylist.txt") in paths

        # we deleted 1 file, we expect the deleted() generator to return only 1 diff
        diffs = list(viewer.deleted())
        assert len(diffs) == 1
        paths = diff_paths(diffs)
        assert Path("other/data.json") in paths

        # we renamed 1 file, we expect the renamed() generator to return only 1 diff
        diffs = list(viewer.renamed())
        assert len(diffs) == 1
        paths = diff_paths(diffs)
        assert len(paths) == 2  # both old and new file name
        assert Path("ignored.json") in paths
        assert Path("ignored2.json") in paths


def test_diff_viewer_affected_paths(repo_with_diffs: Tuple[Repo, Commit, Commit]):
    """Test affected_path() returns only file paths of changed files."""
    repo, previous_head, new_head = repo_with_diffs
    with DiffViewer(previous_head, new_head) as viewer:
        paths = viewer.affected_paths()
        # we touched 4 files, 1 is a rename so it has two paths (old and new)
        assert len(paths) == 5
        assert Path("other/gbac.rego") in paths
        assert Path("mylist.txt") in paths
        assert Path("other/data.json") in paths
        assert Path("ignored.json") in paths
        assert Path("ignored2.json") in paths


def test_diff_viewer_returns_blob_for_added_file(
    repo_with_diffs: Tuple[Repo, Commit, Commit]
):
    """If we added a file, we expect the blob of the new version to be
    returned."""
    repo, previous_head, new_head = repo_with_diffs
    with DiffViewer(previous_head, new_head) as viewer:
        # added files return a VersionedFile with the blob
        # of the new version of both "added" files and "renamed" files
        # (renames are technically deleting one file and adding another
        # file with identical contents)
        files: List[VersionedFile] = list(viewer.added_files())
        assert len(files) == 2
        paths = file_paths(files)
        assert Path("other/gbac.rego") in paths
        assert Path("ignored2.json") in paths


def test_diff_viewer_returns_blob_for_modified_file(
    repo_with_diffs: Tuple[Repo, Commit, Commit]
):
    """If we modified a file, we expect the blob of the new version to be
    returned."""
    repo, previous_head, new_head = repo_with_diffs
    with DiffViewer(previous_head, new_head) as viewer:
        files: List[VersionedFile] = list(viewer.modified_files())
        assert len(files) == 1
        paths = file_paths(files)
        assert Path("mylist.txt") in paths


def test_diff_viewer_returns_blob_for_deleted_file(
    repo_with_diffs: Tuple[Repo, Commit, Commit]
):
    """If we deleted a file, we expect the blob of the *old* version to be
    returned."""
    repo, previous_head, new_head = repo_with_diffs
    with DiffViewer(previous_head, new_head) as viewer:
        # deleted files return a VersionedFile with the blob
        # of the new version of both "deleted" files and "renamed" files
        # (renames are technically deleting one file and adding another
        # file with identical contents)
        files: List[VersionedFile] = list(viewer.deleted_files())
        assert len(files) == 2
        paths = file_paths(files)
        assert Path("other/data.json") in paths
        assert Path("ignored.json") in paths
