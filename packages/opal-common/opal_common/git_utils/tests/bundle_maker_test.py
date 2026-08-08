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
from typing import List, Tuple

from git import Repo
from git.objects import Commit
from opal_common.git_utils.bundle_maker import BundleMaker
from opal_common.git_utils.commit_viewer import CommitViewer
from opal_common.schemas.policy import PolicyBundle, RegoModule

# Support both OPA and OpenFGA policy files
OPA_FILE_EXTENSIONS = [".rego"]
OPENFGA_FILE_EXTENSIONS = [".json", ".yaml"]
ALL_POLICY_EXTENSIONS = [".rego", ".json", ".yaml"]


def assert_is_complete_bundle(bundle: PolicyBundle):
    assert bundle.old_hash is None
    assert bundle.deleted_files is None


def test_bundle_maker_only_includes_opa_files(local_repo: Repo, helpers):
    """Test bundle maker on a repo with non-opa files."""
    repo: Repo = local_repo

    # Using ALL_POLICY_EXTENSIONS to support both OPA and OpenFGA
    maker = BundleMaker(
        repo, in_directories=set([Path(".")]), extensions=ALL_POLICY_EXTENSIONS
    )
    commit: Commit = repo.head.commit
    bundle: PolicyBundle = maker.make_bundle(commit)

    assert_is_complete_bundle(bundle)
    assert bundle.hash == commit.hexsha

    # Updated assertions for both OPA and OpenFGA files
    assert len(bundle.manifest) == 6  # Includes both OPA and OpenFGA files
    assert "other/abac.rego" in bundle.manifest
    assert "other/data.json" in bundle.manifest
    assert "rbac.rego" in bundle.manifest
    assert "some/dir/to/file.rego" in bundle.manifest
    assert "ignored.json" in bundle.manifest
    assert "other/some.json" in bundle.manifest

    # Assert data modules
    assert len(bundle.data_modules) == 1
    assert bundle.data_modules[0].path == "other"
    assert bundle.data_modules[0].data == helpers.json_contents()

    # Updated assertions for policy modules to include OpenFGA
    assert len(bundle.policy_modules) == 5  # Updated count
    policy_modules: List[RegoModule] = bundle.policy_modules
    policy_modules.sort(key=lambda el: el.path)

    # Verify both OPA and OpenFGA policies
    assert policy_modules[0].path == "ignored.json"
    assert policy_modules[1].path == "other/abac.rego"
    assert policy_modules[1].package_name == "app.abac"
    assert policy_modules[2].path == "other/some.json"
    assert policy_modules[3].path == "rbac.rego"
    assert policy_modules[3].package_name == "app.rbac"
    assert policy_modules[4].path == "some/dir/to/file.rego"
    assert policy_modules[4].package_name == "envoy.http.public"

    # Verify RBAC content only in OPA modules
    for module in [m for m in policy_modules if m.path.endswith(".rego")]:
        assert "Role-based Access Control (RBAC)" in module.rego


def test_bundle_maker_can_filter_on_directories(local_repo: Repo, helpers):
    """Test bundle maker filtered on directory only returns policy files from
    that directory."""
    repo: Repo = local_repo
    commit: Commit = repo.head.commit

    # Test filtering with both OPA and OpenFGA files
    maker = BundleMaker(
        repo,
        in_directories=set([Path("other")]),
        extensions=ALL_POLICY_EXTENSIONS,
    )
    bundle: PolicyBundle = maker.make_bundle(commit)

    assert_is_complete_bundle(bundle)
    assert bundle.hash == commit.hexsha

    # Updated assertions for filtered directory
    assert (
        len(bundle.manifest) == 3
    )  # Includes both OPA and OpenFGA files in 'other' directory
    assert "other/abac.rego" in bundle.manifest
    assert "other/data.json" in bundle.manifest
    assert "other/some.json" in bundle.manifest
    assert "some/dir/to/file.rego" not in bundle.manifest

    # Data modules should remain the same
    assert len(bundle.data_modules) == 1
    assert bundle.data_modules[0].path == "other"
    assert bundle.data_modules[0].data == helpers.json_contents()

    # Updated policy module assertions
    assert len(bundle.policy_modules) == 2  # Both OPA and OpenFGA files

    assert bundle.policy_modules[0].path == "other/abac.rego"
    assert bundle.policy_modules[0].package_name == "app.abac"
    assert bundle.policy_modules[1].path == "other/some.json"


def test_bundle_maker_detects_changes_in_source_files(
    repo_with_diffs: Tuple[Repo, Commit, Commit]
):
    """See that making changes to the repo results in different bundles."""
    repo, previous_head, new_head = repo_with_diffs
    maker = BundleMaker(
        repo, in_directories=set([Path(".")]), extensions=ALL_POLICY_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_bundle(previous_head)
    assert_is_complete_bundle(bundle)
    assert bundle.hash == previous_head.hexsha

    # Updated assertions for initial state including both OPA and OpenFGA files
    assert len(bundle.manifest) == 6
    assert "other/gbac.rego" not in bundle.manifest
    assert "other/data.json" in bundle.manifest
    assert "ignored.json" in bundle.manifest
    assert "other/some.json" in bundle.manifest

    assert len(bundle.data_modules) == 1
    assert len(bundle.policy_modules) == 5  # Both OPA and OpenFGA modules

    # Check state after changes
    bundle: PolicyBundle = maker.make_bundle(new_head)
    assert_is_complete_bundle(bundle)
    assert bundle.hash == new_head.hexsha

    # Updated assertions for changed state
    assert len(bundle.manifest) == 6
    assert "other/gbac.rego" in bundle.manifest
    assert "other/data.json" not in bundle.manifest
    assert "ignored2.json" in bundle.manifest  # New OpenFGA file

    assert len(bundle.data_modules) == 0
    assert len(bundle.policy_modules) == 6  # Updated count for both types


def test_bundle_maker_diff_bundle(repo_with_diffs: Tuple[Repo, Commit, Commit]):
    """See that only changes to the repo are returned in a diff bundle."""
    repo, previous_head, new_head = repo_with_diffs
    maker = BundleMaker(
        repo, in_directories=set([Path(".")]), extensions=ALL_POLICY_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_diff_bundle(previous_head, new_head)

    assert bundle.hash == new_head.hexsha
    assert bundle.old_hash == previous_head.hexsha

    # Modified files include both OPA and OpenFGA changes
    assert len(bundle.manifest) == 2
    assert "other/gbac.rego" in bundle.manifest
    assert "ignored2.json" in bundle.manifest

    assert len(bundle.data_modules) == 0
    assert len(bundle.policy_modules) == 2

    # Verify changed modules of both types
    policy_modules = bundle.policy_modules
    policy_modules.sort(key=lambda el: el.path)
    assert policy_modules[0].path == "ignored2.json"  # OpenFGA
    assert policy_modules[1].path == "other/gbac.rego"  # OPA
    assert policy_modules[1].package_name == "app.gbac"
    assert "Role-based Access Control (RBAC)" in policy_modules[1].rego

    # Verify deleted files tracking
    assert bundle.deleted_files is not None
    assert len(bundle.deleted_files.policy_modules) == 1
    assert len(bundle.deleted_files.data_modules) == 1
    assert bundle.deleted_files.data_modules[0] == Path("other")


def test_bundle_maker_sorts_according_to_explicit_manifest(local_repo: Repo, helpers):
    """Test bundle maker filtered on directory only returns policy files from
    that directory."""
    repo: Repo = local_repo
    root = Path(repo.working_tree_dir)
    manifest_path = root / ".manifest"

    # Create manifest with sorting for both types
    helpers.create_new_file_commit(
        repo,
        manifest_path,
        contents="\n".join(["other/abac.rego", "rbac.rego"]),
    )

    commit: Commit = repo.head.commit

    maker = BundleMaker(
        repo, in_directories=set([Path(".")]), extensions=ALL_POLICY_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_bundle(commit)

    assert_is_complete_bundle(bundle)
    assert bundle.hash == commit.hexsha

    # Updated assertions for sorted manifest including both types
    assert len(bundle.manifest) == 6
    assert "other/abac.rego" == bundle.manifest[0]
    assert "rbac.rego" == bundle.manifest[1]
    assert "other/data.json" in bundle.manifest
    assert "some/dir/to/file.rego" in bundle.manifest
    assert "ignored.json" in bundle.manifest
    assert "other/some.json" in bundle.manifest

    # Test different sorting
    helpers.create_delete_file_commit(repo, manifest_path)
    helpers.create_new_file_commit(
        repo,
        manifest_path,
        contents="\n".join(["some/dir/to/file.rego", "other/abac.rego"]),
    )

    commit: Commit = repo.head.commit

    bundle: PolicyBundle = maker.make_bundle(commit)
    assert_is_complete_bundle(bundle)
    assert bundle.hash == commit.hexsha

    # Verify new sorting with both types
    assert len(bundle.manifest) == 6
    assert "some/dir/to/file.rego" == bundle.manifest[0]
    assert "other/abac.rego" == bundle.manifest[1]
    assert "rbac.rego" in bundle.manifest
    assert "other/data.json" in bundle.manifest
    assert "ignored.json" in bundle.manifest
    assert "other/some.json" in bundle.manifest


def test_bundle_maker_sorts_according_to_explicit_manifest_nested(
    local_repo: Repo, helpers
):
    """Test bundle maker with nested manifests handling both OPA and OpenFGA
    files."""
    repo: Repo = local_repo
    root = Path(repo.working_tree_dir)

    # Create nested manifests including both types
    helpers.create_new_file_commit(
        repo,
        root / ".manifest",
        contents="\n".join(
            ["other/data.json", "some/dir", "other", "rbac.rego", "some"]
        ),
    )
    helpers.create_new_file_commit(
        repo,
        root / "other/.manifest",
        contents="\n".join(["data.json", "abac.rego", "some.json"]),
    )
    helpers.create_new_file_commit(
        repo, root / "some/dir/.manifest", contents="\n".join(["to"])
    )
    helpers.create_new_file_commit(
        repo, root / "some/dir/to/.manifest", contents="\n".join(["file.rego"])
    )

    commit: Commit = repo.head.commit

    maker = BundleMaker(
        repo, in_directories=set([Path(".")]), extensions=ALL_POLICY_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_bundle(commit)

    assert_is_complete_bundle(bundle)
    assert bundle.hash == commit.hexsha

    # Updated manifest order verification for both types
    assert bundle.manifest == [
        "other/data.json",
        "some/dir/to/file.rego",
        "other/abac.rego",
        "other/some.json",  # Added OpenFGA file
        "rbac.rego",
        "ignored.json",  # Added OpenFGA file
    ]


def test_bundle_maker_can_ignore_files_using_a_glob_path(local_repo: Repo, helpers):
    """Test bundle maker with ignore glob for both OPA and OpenFGA files."""
    repo: Repo = local_repo
    commit: Commit = repo.head.commit

    maker = BundleMaker(
        repo,
        in_directories=set([Path(".")]),
        extensions=ALL_POLICY_EXTENSIONS,
        bundle_ignore=["other/**"],
    )
    bundle: PolicyBundle = maker.make_bundle(commit)

    assert_is_complete_bundle(bundle)
    assert bundle.hash == commit.hexsha

    # Updated assertions for non-ignored files of both types
    assert len(bundle.manifest) == 3
    assert "rbac.rego" in bundle.manifest
    assert "some/dir/to/file.rego" in bundle.manifest
    assert "ignored.json" in bundle.manifest

    assert len(bundle.data_modules) == 0
    assert len(bundle.policy_modules) == 3

    # Verify remaining modules of both types
    policy_modules: List[RegoModule] = bundle.policy_modules
    policy_modules.sort(key=lambda el: el.path)

    assert policy_modules[0].path == "ignored.json"  # OpenFGA
    assert policy_modules[1].path == "rbac.rego"  # OPA
    assert policy_modules[1].package_name == "app.rbac"
    assert policy_modules[2].path == "some/dir/to/file.rego"  # OPA
    assert policy_modules[2].package_name == "envoy.http.public"

    # Test different ignore pattern
    maker = BundleMaker(
        repo,
        in_directories=set([Path(".")]),
        extensions=ALL_POLICY_EXTENSIONS,
        bundle_ignore=["*.json"],  # Ignore all JSON files
    )
    bundle: PolicyBundle = maker.make_bundle(commit)

    assert_is_complete_bundle(bundle)
    assert bundle.hash == commit.hexsha

    # Verify only non-JSON files remain
    assert len(bundle.manifest) == 3
    assert "other/abac.rego" in bundle.manifest
    assert "rbac.rego" in bundle.manifest
    assert "some/dir/to/file.rego" in bundle.manifest

    assert len(bundle.data_modules) == 0
    assert len(bundle.policy_modules) == 3
