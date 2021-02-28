from opal.common.git.bundle_maker import BundleMaker
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pathlib import Path

from git import Repo

from opal.common.logger import get_logger
from opal.common.git.repo_utils import GitActions
from opal.common.git.commit_viewer import CommitViewer
from opal.common.paths import PathUtils
from opal.common.schemas.policy import PolicyBundle
from opal.server.config import (
    POLICY_REPO_CLONE_PATH,
    OPA_FILE_EXTENSIONS
)

logger = get_logger("Policy API")
router = APIRouter()

async def get_repo(
    repo_path: str = POLICY_REPO_CLONE_PATH,
) -> Repo:
    git_path = Path(repo_path) / Path(".git")
    # TODO: fix this by signaling that the repo is ready
    if not git_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="policy repo was not found"
        )
    return Repo(repo_path)


def normalize_path(path: str) -> Path:
    return Path(path[1:]) if path.startswith('/') else Path(path)

async def get_input_paths_or_throw(
    repo: Repo = Depends(get_repo),
    paths: Optional[List[str]] = Query(None, alias="path")
) -> List[Path]:
    """
    validates the :path query param, and return valid paths.
    if an invalid path is provided, will throw 404.
    """
    paths = paths or []
    paths = [normalize_path(p) for p in paths]

    # verify all input paths exists under the commit hash
    with CommitViewer(repo.head.commit) as viewer:
        for path in paths:
            if not viewer.exists(path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"requested path {path} was not found in the policy repo!"
                )

    # the default of GET /policy (without path params) is to return all
    # the (opa) files in the repo.
    paths = paths or [Path(".")]
    return paths

@router.get("/policy", response_model=PolicyBundle)
async def get_policy(
    repo: Repo = Depends(get_repo),
    input_paths: List[Path] = Depends(get_input_paths_or_throw),
):
    maker = BundleMaker(
        repo,
        in_directories=set(input_paths),
        extensions=OPA_FILE_EXTENSIONS
    )
    return maker.make_bundle(repo.head.commit)