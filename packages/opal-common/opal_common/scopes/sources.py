from typing import List, Any

from pydantic import BaseModel, Field


class SourceAuthData(BaseModel):
    auth_type: str


class SSHAuthData(SourceAuthData):
    username: str
    public_key: str
    private_key: str


class GitHubTokenAuthData(SourceAuthData):
    token: str


class UserPassAuthData(SourceAuthData):
    username: str
    password: str


class PolicySource(BaseModel):
    source_type: str
    url: str
    directories: List[str] = ['.']
    manifest: str = Field('.manifest', description='path to manifest file')
    settings: Any = Field({}, description="source type-specific configuration")


class GitPolicySource(PolicySource):
    auth: SourceAuthData
    branch: str = Field('main', description='Git branch to track')
