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

    def calculate_size(self) -> int:
        """Calculates the size of the policy bundle."""
        size = 0
        if self.data_modules:
            size += len(self.data_modules)
        if self.policy_modules:
            size += len(self.policy_modules)
        if self.deleted_files:
            if self.deleted_files.data_modules:
                size += len(self.deleted_files.data_modules)
            if self.deleted_files.policy_modules:
                size += len(self.deleted_files.policy_modules)
        return size


class PolicyUpdateMessage(BaseSchema):
    old_policy_hash: str
    new_policy_hash: str
    changed_directories: List[str]


class PolicyUpdateMessageNotification(BaseSchema):
    update: PolicyUpdateMessage
    topics: List[str]
