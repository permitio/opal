import os
import sys
from pathlib import Path
from typing import Dict, List, Set

import pytest
from git import GitCommandError, Repo
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


def _write_bundle(bundle_path: Path, files: Dict[str, str]):
    source = bundle_path.parent / f"{bundle_path.name}.files"
    with tarsafe.open(bundle_path, "w:gz") as tar:
        for name, contents in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
            tar.add(path, arcname=name)


def _committed_files(clone_path: Path) -> Set[str]:
    tree = Repo(clone_path).head.commit.tree
    return {blob.path for blob in tree.traverse() if blob.type == "blob"}


def _commit_bundles(tmp_path: Path, bundles: List[Dict[str, str]], pattern="*"):
    """Commits each bundle in turn, as the API source does on each new one."""
    clone_path = tmp_path / "clone"
    for index, files in enumerate(bundles):
        bundle_path = tmp_path / f"bundle-{index}.tar.gz"
        _write_bundle(bundle_path, files)
        extractor = TarFileToLocalGitExtractor(str(clone_path), bundle_path, pattern)
        if index == 0:
            extractor.create_local_git()
        else:
            extractor.extract_bundle_to_local_git(f"bundle {index}")
    return _committed_files(clone_path)


def test_the_default_pattern_commits_top_level_dotfiles(tmp_path):
    files = {"policy.rego": "package a", ".manifest": "policy.rego\n"}

    assert _commit_bundles(tmp_path, [files]) == {"policy.rego", ".manifest"}


def test_files_a_gitignore_in_the_bundle_ignores_are_not_committed(tmp_path):
    files = {"policy.rego": "package a", ".gitignore": "*.log\n", "debug.log": "x"}

    assert _commit_bundles(tmp_path, [files]) == {"policy.rego", ".gitignore"}


def test_a_custom_pattern_is_a_git_pathspec_that_matches_in_subfolders(tmp_path):
    files = {"a.rego": "package a", "sub/b.rego": "package b", "data.json": "{}"}

    assert _commit_bundles(tmp_path, [files], pattern="*.rego") == {
        "a.rego",
        "sub/b.rego",
    }


def test_a_policy_deleted_from_a_subfolder_is_deleted(tmp_path):
    first = {"a.rego": "package a", "sub/b.rego": "package b"}
    second = {"a.rego": "package a"}

    assert _commit_bundles(tmp_path, [first, second]) == {"a.rego"}


def test_a_policy_deleted_under_a_custom_pattern_is_deleted(tmp_path):
    first = {"a.rego": "package a", "b.rego": "package b", "data.json": "{}"}
    second = {"a.rego": "package a", "data.json": "{}"}

    assert _commit_bundles(tmp_path, [first, second], pattern="*.rego") == {"a.rego"}


def test_a_pattern_that_matches_no_file_of_the_first_bundle_fails(tmp_path):
    with pytest.raises(GitCommandError, match=r"\*\.rego"):
        _commit_bundles(tmp_path, [{"data.json": "{}"}], pattern="*.rego")


def test_a_pattern_that_starts_with_a_dash_is_a_pathspec(tmp_path):
    files = {"-n": "package dash", "a.rego": "package a"}

    assert _commit_bundles(tmp_path, [files], pattern="-n") == {"-n"}


def _ignore_json_in_user_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config" / "git").mkdir(parents=True)
    (home / ".config" / "git" / "ignore").write_text("*.json\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)


def _ignore_json_in_xdg_files(tmp_path, monkeypatch):
    (tmp_path / "xdg" / "git").mkdir(parents=True)
    (tmp_path / "xdg" / "git" / "ignore").write_text("*.json\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _ignore_json_in_global_config(tmp_path, monkeypatch):
    (tmp_path / "ignore").write_text("*.json\n")
    (tmp_path / "gitconfig").write_text(
        f"[core]\n\texcludesFile = {tmp_path / 'ignore'}\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))


def _ignore_json_in_system_config(tmp_path, monkeypatch):
    (tmp_path / "ignore").write_text("*.json\n")
    (tmp_path / "gitconfig").write_text(
        f"[core]\n\texcludesFile = {tmp_path / 'ignore'}\n"
    )
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "gitconfig"))


def _json_is_text_in_user_attributes(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config" / "git").mkdir(parents=True)
    (home / ".config" / "git" / "attributes").write_text("*.json text\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)


@pytest.mark.parametrize(
    "host_setting",
    [
        _ignore_json_in_user_files,
        _ignore_json_in_xdg_files,
        _ignore_json_in_global_config,
        _ignore_json_in_system_config,
        _json_is_text_in_user_attributes,
    ],
)
def test_the_hosts_git_config_and_files_change_nothing_committed(
    tmp_path, monkeypatch, host_setting
):
    host_setting(tmp_path, monkeypatch)
    files = {"a.rego": "package a", "data.json": '{\r\n"a": 1\r\n}\r\n'}

    assert _commit_bundles(tmp_path, [files]) == {"a.rego", "data.json"}
    blob = Repo(tmp_path / "clone").head.commit.tree / "data.json"
    assert blob.data_stream.read() == files["data.json"].encode()


def test_a_gitignore_leaves_a_file_an_earlier_bundle_committed_tracked(tmp_path):
    first = {"a.rego": "package a", "d.json": "{}"}
    second = {"a.rego": "package a", "d.json": '{"new": 1}', ".gitignore": "*.json\n"}

    assert _commit_bundles(tmp_path, [first, second]) == {
        "a.rego",
        "d.json",
        ".gitignore",
    }
    blob = Repo(tmp_path / "clone").head.commit.tree / "d.json"
    assert blob.data_stream.read() == b'{"new": 1}'


def test_a_later_bundle_fails_when_the_pattern_matches_nothing_in_it_or_the_last_commit(
    tmp_path,
):
    bundles = [
        {"a.rego": "package a", "d.json": "{}"},
        {"d.json": "{}"},
        {"d.json": "{}"},
    ]

    with pytest.raises(GitCommandError, match=r"\*\.rego"):
        _commit_bundles(tmp_path, bundles, pattern="*.rego")
