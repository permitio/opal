from typing import List, Any

from pydantic import BaseModel, Field


class SourceAuthData(BaseModel):
    auth_type: str = Field(..., description='Authentication type (user/pass, ssh keys, etc)')


class SSHAuthData(SourceAuthData):
    username: str = Field(..., description='SSH username')
    public_key: str = Field(..., description='SSH public key')
    private_key: str = Field(..., description='SSH private key')


class GitHubTokenAuthData(SourceAuthData):
    token: str = Field(..., description='Github Personal Access Token (PAI)')


class UserPassAuthData(SourceAuthData):
    username: str = Field(..., description='Username')
    password: str = Field(..., description='Password')


class PolicySource(BaseModel):
    source_type: str = Field(..., description='Policy source type (e.g. git)')
    url: str = Field(..., description='Policy source URL')
    directories: List[str] = Field(['.'], description='Directories to include')
    manifest: str = Field('.manifest', description='path to manifest file')
    settings: Any = Field({}, description="source type-specific configuration")


class GitPolicySource(PolicySource):
    auth: SourceAuthData = Field(..., description='Authentication data')
    branch: str = Field('main', description='Git branch to track')
