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

from git import Repo
from opal_common.confi import Confi
from opal_common.git.exceptions import GitFailed
from opal_common.git.repo_cloner import RepoCloner

VALID_REPO_REMOTE_URL_HTTPS = "https://github.com/permitio/fastapi_websocket_pubsub.git"

VALID_REPO_REMOTE_URL_SSH = "git@github.com:permitio/fastapi_websocket_pubsub.git"

INVALID_REPO_REMOTE_URL = "git@github.com:permitio/no_such_repo.git"


@pytest.mark.asyncio
async def test_repo_cloner_clone_local_repo(local_repo: Repo):
    """checks that the cloner can handle a local repo url."""
    repo: Repo = local_repo

    root: str = repo.working_tree_dir
    target_path: str = Path(root).parent / "target"

    result = await RepoCloner(repo_url=root, clone_path=target_path).clone()

    assert Path(result.repo.working_tree_dir) == target_path


@pytest.mark.asyncio
async def test_repo_cloner_clone_remote_repo_https_url(tmp_path):
    """Cloner can handle a valid remote git url (https:// scheme)"""
    target_path: Path = tmp_path / "target"
    result = await RepoCloner(
        repo_url=VALID_REPO_REMOTE_URL_HTTPS, clone_path=target_path
    ).clone()
    assert Path(result.repo.working_tree_dir) == target_path


@pytest.mark.asyncio
async def test_repo_cloner_clone_remote_repo_ssh_url(tmp_path):
    """Cloner can handle a valid remote git url (ssh scheme)"""
    target_path: Path = tmp_path / "target"

    # fastapi_websocket_pubsub is a *public* repository, however
    # accessing with an ssh url always demands a valid ssh key.
    # when running in CI (github actions) the actions machine does
    # not have access to the ssh key of a valid user, causing the
    # clone to fail.
    # we could store a real secret in the repo secret, but it's probably
    # not smart/secure enough since the secret is decrypted on the actions runner
    # machine. thus we simply expect the clone to fail when running in ci.
    confi = Confi(is_model=False)
    running_in_ci = confi.bool("CI", False) or confi.bool("GITHUB_ACTIONS", False)

    if running_in_ci:
        with pytest.raises(GitFailed):
            # result =
            await RepoCloner(
                repo_url=VALID_REPO_REMOTE_URL_SSH,
                clone_path=target_path,
                clone_timeout=5,
            ).clone()
    else:
        result = await RepoCloner(
            repo_url=VALID_REPO_REMOTE_URL_SSH, clone_path=target_path
        ).clone()
        assert Path(result.repo.working_tree_dir) == target_path


@pytest.mark.asyncio
async def test_repo_cloner_clone_fail_on_invalid_remote_url(tmp_path):
    """if remote url is invalid, cloner will retry with tenacity until the last
    attempt is failed, and then throw GitFailed."""
    target_path: Path = tmp_path / "target"
    with pytest.raises(GitFailed):
        await RepoCloner(
            repo_url=INVALID_REPO_REMOTE_URL, clone_path=target_path, clone_timeout=5
        ).clone()
