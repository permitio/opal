from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pathlib import Path

from git import Repo

from opal.common.logger import get_logger
from opal.server.config import (
    POLICY_REPO_CLONE_PATH,
    OPA_FILE_EXTENSIONS
)
from opal.common.git.repo_utils import GitActions
from opal.common.schemas.policy import PolicyBundle

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

async def get_parent_dirs_from_paths(
    repo: Repo = Depends(get_repo),
    path: Optional[List[str]] = Query(None)
) -> List[Path]:
    repo_dir = GitActions.repo_dir(repo)
    paths = path or []
    parents = []

    for p in paths:
        if p.startswith('/'):
            p = p[1:] # remove first slash
        repo_path = repo_dir / Path(p)
        if not repo_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"requested path {p} was not found in the policy repo!"
            )
        parents.append(repo_path)

    # the default of GET /policy (without path params) is to return all
    # the (opa) files in the repo.
    if not parents:
        parents = [repo_dir]

    return parents

@router.get("/policy", response_model=PolicyBundle)
async def get_policy(
    repo: Repo = Depends(get_repo),
    parent_dirs: List[Path] = Depends(get_parent_dirs_from_paths),
):
    return GitActions.create_bundle(
        repo,
        repo.head.commit,
        parent_dirs,
        extensions=OPA_FILE_EXTENSIONS
    )