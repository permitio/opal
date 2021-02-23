from typing import List
from pydantic import BaseModel, Field


class BaseSchema(BaseModel):
    class Config:
        orm_mode = True

class DataModule(BaseSchema):
    path: str = Field(..., description="where to place the data module relative to opa data root")
    data: str = Field(..., description="data module file contents (json)")

class RegoModule(BaseSchema):
    path: str = Field(..., description="path of policy module on disk, will be used to generate policy id")
    package_name: str = Field(..., description="opa module package name")
    rego: str = Field(..., description="rego module file contents (text)")

class PolicyBundle(BaseSchema):
    manifest: List[str]
    hash: str = Field(..., description="commit hash (debug version)")
    data_modules: List[DataModule]
    rego_modules: List[RegoModule]