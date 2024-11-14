from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class BaseSchema(BaseModel):
    class Config:
        orm_mode = True


class DataModule(BaseSchema):
    path: str = Field(
        ..., description="where to place the data module relative to opa data root"
    )
    data: str = Field(..., description="data module file contents (json)")


class RegoModule(BaseSchema):
    path: str = Field(
        ...,
        description="path of policy module on disk, will be used to generate policy id",
    )
    package_name: str = Field(..., description="opa module package name")
    rego: str = Field(..., description="rego module file contents (text)")


class DeletedFiles(BaseSchema):
    data_modules: List[Path] = []
    policy_modules: List[Path] = []


class PolicyBundle(BaseSchema):
    manifest: List[str]
    hash: str = Field(..., description="commit hash (debug version)")
    old_hash: Optional[str] = Field(
        None, description="old commit hash (in diff bundles)"
    )
    data_modules: List[DataModule]
    policy_modules: List[RegoModule]
    deleted_files: Optional[DeletedFiles]


class PolicyUpdateMessage(BaseSchema):
    old_policy_hash: str
    new_policy_hash: str
    changed_directories: List[str]


class PolicyUpdateMessageNotification(BaseSchema):
    update: PolicyUpdateMessage
    topics: List[str]
