import os
import sys

from git import Repo
from opal_common.security import tarsafe

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

from opal_common.git_utils.tar_file_to_local_git_extractor import (
    TarFileToLocalGitExtractor,
)


def test_extract_bundle_to_local_git_stages_deleted_policy_files(
    local_repo: Repo, tmp_path, helpers
):
    """Deleted files in a new API bundle should be deleted in the local git
    repo."""
    empty_bundle_path = tmp_path / "empty_bundle.tar.gz"
    new_policy_file = "policy.cedar"
    new_policy_content = "permit (principal, action, resource);"

    # Create a new tar.gz with only one file and extract it to local git repo
    with tarsafe.open(empty_bundle_path, "w:gz") as tar:
        file_path = empty_bundle_path.parent / new_policy_file
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(new_policy_content)
        tar.add(file_path, arcname=new_policy_file)
    extractor = TarFileToLocalGitExtractor(
        local_repo.working_tree_dir, empty_bundle_path
    )
    _local_git, prev_commit, new_commit = extractor.extract_bundle_to_local_git(
        "Update bundle"
    )

    # Assert that after extraction, unrelated files is local git repo are deleted and leaving only the single file
    prev_files = {
        blob.path for blob in prev_commit.tree.traverse() if blob.type == "blob"
    }
    new_files = {
        blob.path for blob in new_commit.tree.traverse() if blob.type == "blob"
    }
    assert new_policy_file not in prev_files
    assert new_policy_file in new_files
    assert len(prev_files) > 1
    assert len(new_files) == 1
