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
    )
)
sys.path.append(root_dir)

from pathlib import Path
from git import Repo

from opal_common.git.repo_cloner import RepoCloner
from opal_common.git.exceptions import GitFailed
from opal_common.confi import Confi

VALID_REPO_REMOTE_URL_HTTPS = \
    "https://github.com/authorizon/fastapi_websocket_pubsub.git"

VALID_REPO_REMOTE_URL_SSH = \
    "git@github.com:authorizon/fastapi_websocket_pubsub.git"

INVALID_REPO_REMOTE_URL = "git@github.com:authorizon/no_such_repo.git"

def test_repo_cloner_clone_local_repo(local_repo: Repo):
    """
    checks that the cloner can handle a local repo url
    """
    repo: Repo = local_repo

    root: str = repo.working_tree_dir
    target_path: str = Path(root).parent / "target"

    result = RepoCloner(
        repo_url=root,
        clone_path=target_path
    ).clone()

    assert result.cloned_from_remote == True
    assert Path(result.repo.working_tree_dir) == target_path

def test_repo_cloner_when_local_repo_already_exist(local_repo: Repo):
    """
    Cloner will ignore the remote url and will init
    from a valid local repo found on the target path
    """
    repo: Repo = local_repo

    target_path = Path(repo.working_tree_dir)
    result = RepoCloner(
        repo_url=VALID_REPO_REMOTE_URL_HTTPS,
        clone_path=target_path,
    ).clone()
    assert result.cloned_from_remote == False
    assert Path(result.repo.working_tree_dir) == target_path
    assert result.repo == repo

def test_repo_cloner_fails_on_fake_local_repo(tmp_path):
    """
    Cloner will fail (throw GitFailed) when a non-repo or a
    corrupted repo exists in the target path for cloning
    """
    target_path: Path = tmp_path / "target"
    target_path.mkdir()

    with open(target_path / ".git", "w+") as f:
        f.write("fake .git file: simulates corrupted repo")

    with pytest.raises(GitFailed):
        RepoCloner(
            repo_url=VALID_REPO_REMOTE_URL_HTTPS,
            clone_path=target_path
        ).clone()

def test_repo_cloner_clone_remote_repo_https_url(tmp_path):
    """
    Cloner can handle a valid remote git url (https:// scheme)
    """
    target_path: Path = tmp_path / "target"
    result = RepoCloner(
        repo_url=VALID_REPO_REMOTE_URL_HTTPS,
        clone_path=target_path
    ).clone()
    assert result.cloned_from_remote == True
    assert Path(result.repo.working_tree_dir) == target_path

def test_repo_cloner_clone_remote_repo_ssh_url(tmp_path):
    """
    Cloner can handle a valid remote git url (ssh scheme)
    """
    target_path: Path = tmp_path / "target"

    # fastapi_websocket_pubsub is a *public* repository, however
    # accessing with an ssh url always demands a valid ssh key.
    # when running in CI (github actions) the actions machine does
    # not have access to the ssh key of a valid user, causing the
    # clone to fail.
    # we could store a real secret in the repo secret, but it's probably
    # not smart/secure enough since the secret is decrypted on the actions runner
    # machine. thus we simply expect the clone to fail when running in ci.
    confi = Confi()
    running_in_ci = confi.bool("CI", False) or confi.bool("GITHUB_ACTIONS", False)

    if running_in_ci:
        with pytest.raises(GitFailed):
            # result =
            RepoCloner(
                repo_url=VALID_REPO_REMOTE_URL_SSH,
                clone_path=target_path
            ).clone()
    else:
        result = RepoCloner(
            repo_url=VALID_REPO_REMOTE_URL_SSH,
            clone_path=target_path
        ).clone()
        assert result.cloned_from_remote == True
        assert Path(result.repo.working_tree_dir) == target_path

def test_repo_cloner_clone_fail_on_invalid_remote_url(tmp_path):
    """
    if remote url is invalid, cloner will retry with tenacity
    until the last attempt is failed, and then throw GitFailed
    """
    target_path: Path = tmp_path / "target"
    with pytest.raises(GitFailed):
        RepoCloner(
            repo_url=INVALID_REPO_REMOTE_URL,
            clone_path=target_path
        ).clone()