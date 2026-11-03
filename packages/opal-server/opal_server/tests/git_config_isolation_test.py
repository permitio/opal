"""The test session reads no git config of the machine running it (see the root
conftest.py): not through git, and not through libgit2."""

import os
import shutil
import subprocess

import pygit2
import pytest


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_reads_no_system_or_global_config(tmp_path):
    assert os.environ["GIT_CONFIG_NOSYSTEM"] == "1"
    listed = subprocess.run(
        ["git", "config", "--list", "--show-origin"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert listed.stdout == "", listed.stdout


def test_libgit2_reads_no_global_xdg_or_system_config(tmp_path):
    repo = pygit2.init_repository(str(tmp_path / "repo"))
    try:
        # Only what init wrote into the repository's own config.
        assert {entry.level for entry in repo.config} == {
            pygit2.enums.ConfigLevel.LOCAL
        }
        assert repo.head_is_unborn
        assert repo.references["HEAD"].target == "refs/heads/master"
    finally:
        repo.free()
