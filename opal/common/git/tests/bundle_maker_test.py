import pytest
import os
import sys

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)

from typing import List, Tuple
from pathlib import Path
from git import Repo
from git.objects import Commit

from opal.common.git.bundle_maker import BundleMaker
from opal.common.schemas.policy import PolicyBundle, RegoModule

OPA_FILE_EXTENSIONS = ('.rego', '.json')

def assert_is_complete_bundle(bundle: PolicyBundle):
    assert bundle.old_hash is None
    assert bundle.deleted_files is None

def test_bundle_maker_only_includes_opa_files(local_repo: Repo, helpers):
    """
    Test bundle maker on a repo with non-opa files
    """
    repo: Repo = local_repo

    maker = BundleMaker(
        repo,
        in_directories=set([Path('.')]),
        extensions=OPA_FILE_EXTENSIONS
    )
    commit: Commit = repo.head.commit
    bundle: PolicyBundle = maker.make_bundle(commit)
    # assert the bundle is a complete bundle (no old hash, etc)
    assert_is_complete_bundle(bundle)
    # assert the commit hash is correct
    assert bundle.hash == commit.hexsha
    # assert the manifest only includes opa files
    # the source repo contains 3 rego files and 1 data.json file
    # the bundler ignores files like "some.json" and "mylist.txt"
    assert len(bundle.manifest) == 4
    assert "other/abac.rego" in bundle.manifest
    assert "other/data.json" in bundle.manifest
    assert "rbac.rego" in bundle.manifest
    assert "some/dir/to/file.rego" in bundle.manifest

    # assert on the contents of data modules
    assert len(bundle.data_modules) == 1
    assert bundle.data_modules[0].path == "other"
    assert bundle.data_modules[0].data == helpers.json_contents()

    # assert on the contents of policy modules
    assert len(bundle.policy_modules) == 3
    policy_modules: List[RegoModule] = bundle.policy_modules
    policy_modules.sort(key=lambda el: el.path)

    assert policy_modules[0].path == "other/abac.rego"
    assert policy_modules[0].package_name == "app.abac"

    assert policy_modules[1].path == "rbac.rego"
    assert policy_modules[1].package_name == "app.rbac"

    assert policy_modules[2].path == "some/dir/to/file.rego"
    assert policy_modules[2].package_name == "envoy.http.public"

    for module in policy_modules:
        assert "Role-based Access Control (RBAC)" in module.rego

def test_bundle_maker_can_filter_on_directories(local_repo: Repo, helpers):
    """
    Test bundle maker filtered on directory only returns opa files from that directory
    """
    repo: Repo = local_repo
    commit: Commit = repo.head.commit

    maker = BundleMaker(
        repo,
        in_directories=set([Path('other')]),
        extensions=OPA_FILE_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_bundle(commit)
    # assert the bundle is a complete bundle (no old hash, etc)
    assert_is_complete_bundle(bundle)
    # assert the commit hash is correct
    assert bundle.hash == commit.hexsha

    # assert only filter directory files are in the manifest
    assert len(bundle.manifest) == 2
    assert "other/abac.rego" in bundle.manifest
    assert "other/data.json" in bundle.manifest
    assert "some/dir/to/file.rego" not in bundle.manifest

    # assert on the contents of data modules
    assert len(bundle.data_modules) == 1
    assert bundle.data_modules[0].path == "other"
    assert bundle.data_modules[0].data == helpers.json_contents()

    # assert on the contents of policy modules
    assert len(bundle.policy_modules) == 1

    assert bundle.policy_modules[0].path == "other/abac.rego"
    assert bundle.policy_modules[0].package_name == "app.abac"

    maker = BundleMaker(
        repo,
        in_directories=set([Path('some')]),
        extensions=OPA_FILE_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_bundle(commit)
    # assert the bundle is a complete bundle (no old hash, etc)
    assert_is_complete_bundle(bundle)
    # assert the commit hash is correct
    assert bundle.hash == commit.hexsha

    # assert only filter directory files are in the manifest
    assert len(bundle.manifest) == 1
    assert "some/dir/to/file.rego" in bundle.manifest

    # assert on the contents of data modules
    assert len(bundle.data_modules) == 0

    # assert on the contents of policy modules
    assert len(bundle.policy_modules) == 1

    assert bundle.policy_modules[0].path == "some/dir/to/file.rego"
    assert bundle.policy_modules[0].package_name == "envoy.http.public"

def test_bundle_maker_detects_changes_in_source_files(repo_with_diffs: Tuple[Repo, Commit, Commit]):
    """
    See that making changes to the repo results in different bundles
    """
    repo, previous_head, new_head = repo_with_diffs
    maker = BundleMaker(
        repo,
        in_directories=set([Path('.')]),
        extensions=OPA_FILE_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_bundle(previous_head)
    assert_is_complete_bundle(bundle)
    # assert the commit hash is correct
    assert bundle.hash == previous_head.hexsha

    # assert on manifest contents
    assert len(bundle.manifest) == 4
    assert "other/gbac.rego" not in bundle.manifest
    assert "other/data.json" in bundle.manifest

    # assert on the contents of data modules
    assert len(bundle.data_modules) == 1

    # assert on the contents of policy modules
    assert len(bundle.policy_modules) == 3

    # now in the new head, other/gbac.rego was added and other/data.json was deleted
    bundle: PolicyBundle = maker.make_bundle(new_head)
    assert_is_complete_bundle(bundle)
    # assert the commit hash is correct
    assert bundle.hash == new_head.hexsha

    # assert on manifest contents
    assert len(bundle.manifest) == 4
    assert "other/gbac.rego" in bundle.manifest
    assert "other/data.json" not in bundle.manifest

    # assert on the contents of data modules
    assert len(bundle.data_modules) == 0

    # assert on the contents of policy modules
    assert len(bundle.policy_modules) == 4

def test_bundle_maker_diff_bundle(repo_with_diffs: Tuple[Repo, Commit, Commit]):
    """
    See that only changes to the repo are returned in a diff bundle
    """
    repo, previous_head, new_head = repo_with_diffs
    maker = BundleMaker(
        repo,
        in_directories=set([Path('.')]),
        extensions=OPA_FILE_EXTENSIONS
    )
    bundle: PolicyBundle = maker.make_diff_bundle(previous_head, new_head)
    # assert both hashes are included
    assert bundle.hash == new_head.hexsha
    assert bundle.old_hash == previous_head.hexsha

    # assert manifest only returns modified files that are not deleted
    assert len(bundle.manifest) == 1
    assert "other/gbac.rego" in bundle.manifest

    # assert on the contents of data modules
    assert len(bundle.data_modules) == 0
    assert len(bundle.policy_modules) == 1

    assert bundle.policy_modules[0].path == "other/gbac.rego"
    assert bundle.policy_modules[0].package_name == "app.gbac"
    assert "Role-based Access Control (RBAC)" in bundle.policy_modules[0].rego

    # assert bundle.deleted_files only includes deleted files
    assert bundle.deleted_files is not None
    assert len(bundle.deleted_files.policy_modules) == 0
    assert len(bundle.deleted_files.data_modules) == 1
    assert bundle.deleted_files.data_modules[0] == Path("other") # other/data.json was deleted
