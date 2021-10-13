import os
from pathlib import Path
import shutil
from typing import List, Optional
import git
from pydantic.error_wrappers import ValidationError

from opal_common.security.tarsafe import TarSafe
from opal_server.config import opal_server_config


def commit_local_git(local_clone_path: str, init_commit_msg: str = "Init", should_init: bool = False):
    if should_init:
        local_git = git.Repo.init(local_clone_path)  #  loads git if exist
    else:
        local_git = git.Repo(local_clone_path)
    prev_commit = None
    if len(local_git.index.repo.heads):
        prev_commit = local_git.index.repo.head.commit
    local_git.index.add(opal_server_config.POLICY_BUNDLE_GIT_ADD_PATTERN)
    new_commit = local_git.index.commit(init_commit_msg)
    return local_git, prev_commit, new_commit


def is_git_repo(path) -> Optional[git.Repo]:
    local_git = False
    try:
        local_git = git.Repo(path)
        _ = local_git.git_dir
        return local_git
    except Exception:
        return None


def create_local_git(tmp_bundle_path: Path, local_clone_path: str):
    extract_bundle_tar(tmp_bundle_path, local_clone_path)
    local_git = is_git_repo(local_clone_path)
    if not local_git or len(local_git.heads) == 0:
        local_git = commit_local_git(local_clone_path, should_init=True)
    return local_git


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


def extract_bundle_tar(bundle_path: Path, extract_path: str, mode: str = "r:gz") -> bool:
    with TarSafe.open(bundle_path, mode=mode) as tar_file:
        tar_file_names = tar_file.getnames()
        validate_tar_or_throw(tar_file_names)
        tar_file.extractall(path=extract_path)


def validate_tar_or_throw(tar_file_names: List[str], forbidden_filename: str = '.git'):
    if len(tar_file_names) == 0:
        raise ValidationError("No files in bundle")
    if forbidden_filename and forbidden_filename in tar_file_names:
        raise ValidationError("No {forbidden_filename} files are allowed in OPAL api bundle".format(
            forbidden_filename=forbidden_filename))
