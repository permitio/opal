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
from typing import List

from git import Repo
from git.objects import Commit
from opal_common.git.commit_viewer import CommitViewer, VersionedNode


def node_paths(nodes: List[VersionedNode]) -> List[Path]:
    return [node.path for node in nodes]


def test_commit_viewer_node_filters(local_repo: Repo):
    """Test nodes() generator with and without filters."""
    repo: Repo = local_repo

    with CommitViewer(repo.head.commit) as viewer:
        num_nodes = len(list(viewer.nodes()))

        # assert top-level and in-directory paths are found
        assert Path("rbac.rego") in viewer.paths
        assert Path("some/dir/to/file.rego") in viewer.paths

        # test path filter
        nodes = list(viewer.nodes(lambda node: str(node.path).startswith("some")))
        # assert filtered list is smaller
        assert len(nodes) < num_nodes
        # filter matches only some/dir/to/file.rego
        # assert each level in the hierarchy (which is a separate node) is in the list
        assert len(nodes) == 4
        paths = node_paths(nodes)
        assert Path("some") in paths
        assert Path("some/dir") in paths
        assert Path("some/dir/to") in paths
        assert Path("some/dir/to/file.rego") in paths

        # test extension filter
        nodes = list(viewer.nodes(lambda node: node.path.suffix == ".rego"))
        # this time, the filter only matches file nodes (we have 3 rego files in the dummy repo)
        assert len(nodes) == 3
        paths = node_paths(nodes)
        assert Path("rbac.rego") in paths
        assert Path("other/abac.rego") in paths
        assert Path("some/dir/to/file.rego") in paths


def test_commit_viewer_file_filters(local_repo: Repo):
    """Check files() returns only the file paths we expect (and no directory
    paths)"""
    repo: Repo = local_repo

    with CommitViewer(repo.head.commit) as viewer:
        # assert only files are returned by files()
        # (3 .rego and 3 .json and 1 .txt in dummy repo)
        all_files = list(viewer.files())
        assert len(all_files) == 7

        # assert directories are not in files() results
        paths = node_paths(all_files)
        assert Path("other") not in paths
        assert Path("some") not in paths

        # assert that same filter as before returns 1 entry (because only files are filtered)
        # therefore intermediate directories are not returned
        nodes = list(viewer.files(lambda node: str(node.path).startswith("some")))
        assert len(nodes) == 1

        # slightly different filter does not return the "some" directory, but returns
        # some.json and some/dir/to/file.rego, both are files with "some" in their path
        nodes = list(viewer.files(lambda node: str(node.path).find("some") > -1))
        assert len(nodes) == 2
        paths = node_paths(nodes)
        assert Path("other/some.json") in paths
        assert Path("some/dir/to/file.rego") in paths

        # test extension filter
        nodes = list(viewer.files(lambda node: node.path.suffix == ".rego"))
        assert len(nodes) == 3
        paths = node_paths(nodes)
        assert Path("rbac.rego") in paths
        assert Path("other/abac.rego") in paths
        assert Path("some/dir/to/file.rego") in paths

        # test file name filter
        nodes = list(viewer.files(lambda node: node.path.name == "data.json"))
        assert len(nodes) == 1
        paths = node_paths(nodes)
        assert Path("other/data.json") in paths


def test_commit_viewer_directory_filters(local_repo: Repo):
    """Check directories() returns only the directory paths we expect (and no
    file paths)"""
    repo: Repo = local_repo

    with CommitViewer(repo.head.commit) as viewer:
        # assert only directories are returned
        # ".", "other", "some", "some/dir", "some/dir/to"
        all_directories = list(viewer.directories())
        assert len(all_directories) == 5

        # assert files are not in directories results
        paths = node_paths(all_directories)
        for path in paths:
            assert path.suffix == ""

        # assert that same filter as before returns 3 entries
        # (filter matches only some/dir/to/file.rego) intermediate directories
        nodes = list(viewer.directories(lambda node: str(node.path).startswith("some")))
        assert len(nodes) == 3
        paths = node_paths(nodes)
        assert Path("some/dir/to") in paths
        assert Path("some/dir/to/file.rego") not in paths

        # filter matches some.json and some dir, only some dir is returned
        nodes = list(viewer.directories(lambda node: node.path.name.find("some") > -1))
        assert len(nodes) == 1
        paths = node_paths(nodes)
        assert Path("some") in paths


def test_file_removed_file_does_not_exist(local_repo: Repo, helpers):
    """Check that viewing the repository from the perspective of two different
    commits yields different results.

    More specifically, if in the 2nd commit we removed a file from the
    repo, we will see the file when viewing from the 1st commit
    perspective, and won't see the file from the 2nd commit perspective.
    """
    repo: Repo = local_repo
    previous_head: Commit = repo.head.commit

    with CommitViewer(previous_head) as viewer:
        paths = node_paths(
            list(viewer.files(lambda node: str(node.path).startswith("some")))
        )
        assert len(paths) == 1
        assert Path("some/dir/to/file.rego") in paths

    helpers.create_delete_file_commit(
        local_repo, Path(local_repo.working_tree_dir) / "some/dir/to/file.rego"
    )

    new_head: Commit = repo.head.commit
    assert previous_head != new_head

    with CommitViewer(new_head) as viewer:
        paths = node_paths(
            list(viewer.files(lambda node: str(node.path).startswith("some")))
        )
        assert len(paths) == 0
        assert Path("some/dir/to/file.rego") not in paths
