import os
import shutil
from pathlib import Path
from typing import List, Optional

import git
from opal_common.security.tarsafe import TarSafe
from pydantic.error_wrappers import ValidationError


class TarFileToLocalGitExtractor:
    """This class takes tar file from remote api source and extract it to local
    git, so we could manage update to opal clients.

    Args:
        local_clone_path(str):  path for the local git to manage policies
        tmp_bundle_path(Path):  path to download bundle from api source
    """

    def __init__(
        self,
        local_clone_path: str,
        tmp_bundle_path: Path,
        policy_bundle_git_add_pattern="*",
    ):
        self.local_clone_path = local_clone_path
        self.tmp_bundle_path = tmp_bundle_path
        self.policy_bundle_git_add_pattern = policy_bundle_git_add_pattern

    def commit_local_git(
        self, init_commit_msg: str = "Init", should_init: bool = False
    ):
        """
        Commit first version of bundle or the updates that come after
        Args:
            init_commit_msg(str):  text of the commit msg
            should_init(Path):  should it init the repo or it is existing repo
        """
        if should_init:
            local_git = git.Repo.init(self.local_clone_path)
        else:
            local_git = git.Repo(self.local_clone_path)
        prev_commit = None
        if len(local_git.index.repo.heads):
            prev_commit = local_git.index.repo.head.commit
        local_git.index.add(self.policy_bundle_git_add_pattern)
        new_commit = local_git.index.commit(init_commit_msg)
        return local_git, prev_commit, new_commit

    def create_local_git(self):
        """Extract bundle create local git and commit this initial state."""

        self.extract_bundle_tar()
        local_git = TarFileToLocalGitExtractor.is_git_repo(self.local_clone_path)
        if not local_git or len(local_git.heads) == 0:
            local_git = self.commit_local_git(should_init=True)
        return local_git

    def extract_bundle_to_local_git(self, commit_msg: str):
        """
        Update local git with new bundle
        Args:
            commit_msg(str):  text of the commit msg
        """
        tmp_path = f"{self.local_clone_path}.bak"
        os.rename(self.local_clone_path, tmp_path)
        try:
            self.extract_bundle_tar()
            shutil.move(
                os.path.join(tmp_path, ".git"),
                os.path.join(self.local_clone_path, ".git"),
            )
        finally:
            shutil.rmtree(tmp_path)
        local_git, prev_commit, new_commit = self.commit_local_git(commit_msg)
        return local_git, prev_commit, new_commit

    def extract_bundle_tar(self, mode: str = "r:gz") -> bool:
        """
        Extract bundle tar, tar path is at self.tmp_bundle_path
        Uses TarSafe that checks that our bundle file don't have vulnerabilities like path traversal
        Args:
            mode(str): mode for TarSafe default to r:gz that can open tar.gz files
        """
        with TarSafe.open(self.tmp_bundle_path, mode=mode) as tar_file:
            tar_file_names = tar_file.getnames()
            TarFileToLocalGitExtractor.validate_tar_or_throw(tar_file_names)
            tar_file.extractall(path=self.local_clone_path)

    @staticmethod
    def is_git_repo(path) -> Optional[git.Repo]:
        """
        Checks is this path is a git repo if it is return Repo obj
        Return:
            Repo obj if it is a git repo if not returns None
        """
        local_git = False
        try:
            local_git = git.Repo(path)
            _ = local_git.git_dir
            return local_git
        except Exception:
            return None

    @staticmethod
    def validate_tar_or_throw(
        tar_file_names: List[str], forbidden_filename: str = ".git"
    ):
        if len(tar_file_names) == 0:
            raise ValidationError("No files in bundle")
        if forbidden_filename and forbidden_filename in tar_file_names:
            raise ValidationError(
                "No {forbidden_filename} files are allowed in OPAL api bundle".format(
                    forbidden_filename=forbidden_filename
                )
            )
