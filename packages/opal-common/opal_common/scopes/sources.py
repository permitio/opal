from typing import Optional, Union, List, Any

from pydantic import BaseModel


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
    settings: Any
    directories: List[str] = ['.']


class GitPolicySource(PolicySource):
    auth: SourceAuthData
