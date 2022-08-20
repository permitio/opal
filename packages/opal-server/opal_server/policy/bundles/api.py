import os
from pathlib import Path
from typing import List, Optional

import fastapi.responses
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from git import Repo
from opal_common.confi.confi import load_conf_if_none
from opal_common.git.bundle_maker import BundleMaker
from opal_common.git.commit_viewer import CommitViewer
from opal_common.git.repo_cloner import RepoClonePathFinder
from opal_common.logger import logger
from opal_common.schemas.policy import PolicyBundle
from opal_server.config import opal_server_config
from starlette.responses import RedirectResponse

router = APIRouter()


async def get_repo(
    base_clone_path: str = None,
    clone_subdirectory_prefix: str = None,
    use_fixed_path: bool = None,
) -> Repo:
    base_clone_path = load_conf_if_none(
        base_clone_path, opal_server_config.POLICY_REPO_CLONE_PATH
    )
    clone_subdirectory_prefix = load_conf_if_none(
        clone_subdirectory_prefix, opal_server_config.POLICY_REPO_CLONE_FOLDER_PREFIX
    )
    use_fixed_path = load_conf_if_none(
        use_fixed_path, opal_server_config.POLICY_REPO_REUSE_CLONE_PATH
    )
    clone_path_finder = RepoClonePathFinder(
        base_clone_path=base_clone_path,
        clone_subdirectory_prefix=clone_subdirectory_prefix,
        use_fixed_path=use_fixed_path,
    )
    repo_path = clone_path_finder.get_clone_path()

    policy_repo_not_found_error = HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="policy repo was not found",
    )

    if not repo_path:
        raise policy_repo_not_found_error

    git_path = Path(os.path.join(repo_path, Path(".git")))
    # TODO: at the moment opal server will 503 until it finishes cloning the policy repo
    # we might fix this in the future by signaling to the client that the repo is ready
    if not git_path.exists():
        raise policy_repo_not_found_error
    return Repo(repo_path)


def normalize_path(path: str) -> Path:
    return Path(path[1:]) if path.startswith("/") else Path(path)


async def get_input_paths_or_throw(
    repo: Repo = Depends(get_repo),
    paths: Optional[List[str]] = Query(None, alias="path"),
) -> List[Path]:
    """validates the :path query param, and return valid paths.

    if an invalid path is provided, will throw 404.
    """
    paths = paths or []
    paths = [normalize_path(p) for p in paths]

    # if the repo is currently being cloned - the repo.heads is empty
    if len(repo.heads) == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="policy repo is not ready",
        )

    # verify all input paths exists under the commit hash
    with CommitViewer(repo.head.commit) as viewer:
        for path in paths:
            if not viewer.exists(path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"requested path {path} was not found in the policy repo!",
                )

    # the default of GET /policy (without path params) is to return all
    # the (opa) files in the repo.
    paths = paths or [Path(".")]
    return paths


@router.get("/policy", response_model=PolicyBundle)
async def get_policy(
    repo: Repo = Depends(get_repo),
    input_paths: List[Path] = Depends(get_input_paths_or_throw),
    base_hash: Optional[str] = Query(
        None,
        description="hash of previous bundle already downloaded, server will return a diff bundle.",
    ),
):
    maker = BundleMaker(
        repo,
        in_directories=set(input_paths),
        extensions=opal_server_config.OPA_FILE_EXTENSIONS,
        root_manifest_path=opal_server_config.POLICY_REPO_MANIFEST_PATH,
    )
    # check if commit exist in the repo
    revision = None
    if base_hash:
        try:
            revision = repo.rev_parse(base_hash)
        except ValueError:
            logger.warning(f"base_hash {base_hash} not exist in the repo")

    if revision is None:
        return maker.make_bundle(repo.head.commit)
    try:
        old_commit = repo.commit(base_hash)
        return maker.make_diff_bundle(old_commit, repo.head.commit)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"commit with hash {base_hash} was not found in the policy repo!",
        )
