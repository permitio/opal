import os
from pathlib import Path
import shutil
import git
from pydantic.error_wrappers import ValidationError

from opal_common.security.tarsafe import TarSafe


def create_local_git(tmp_bundle_path: Path, local_clone_path: str):
    extract_bundle_tar(tmp_bundle_path, local_clone_path)
    local_git = commit_local_git(local_clone_path)
    return local_git


def commit_local_git(local_clone_path: str, init_commit_msg: str = "Init"):
    local_git = git.Repo.init(local_clone_path)  #  loads git if exist
    prev_commit = None
    if len(local_git.index.repo.heads):
        prev_commit = local_git.index.repo.head.commit
    local_git.index.add('*')  # maybe only the supported files
    new_commit = local_git.index.commit(init_commit_msg)
    return local_git, prev_commit, new_commit


def update_local_git(local_clone_path: str, tmp_bundle_path: Path, commit_msg: str):
    tmp_path = f"{local_clone_path}.bak"
    os.rename(local_clone_path, tmp_path)
    try:
        extract_bundle_tar(tmp_bundle_path, local_clone_path)
        shutil.move(os.path.join(tmp_path, ".git"), os.path.join(local_clone_path, ".git"))
    finally:
        shutil.rmtree(tmp_path)
    local_git, prev_commit, new_commit = commit_local_git(local_clone_path, commit_msg)
    return local_git, prev_commit, new_commit


def extract_bundle_tar(tmp_bundle_path, path: str, mode: str = "r:gz", forbidden_filename: str = '.git') -> bool:
    with TarSafe.open(tmp_bundle_path, mode=mode) as tar_file:
        tar_file_names = tar_file.getnames()
        if len(tar_file_names) == 0:
            raise ValidationError("No files in bundle")
        if forbidden_filename and forbidden_filename in tar_file_names:
            raise ValidationError("No {forbidden_filename} files are allowed in OPAL api bundle".format(
                forbidden_filename=forbidden_filename))
        else:
            tar_file.extractall(path=path)
    return True
