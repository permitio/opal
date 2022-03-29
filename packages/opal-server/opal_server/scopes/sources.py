from typing import Optional, Union

from pydantic import BaseModel


class ScopeSourceAuthData(BaseModel):
    auth_type: str


class SSHAuthData(ScopeSourceAuthData):
    username: str
    public_key: str
    private_key: str


class GitHubTokenAuthData(ScopeSourceAuthData):
    token: str


class UserPassAuthData(ScopeSourceAuthData):
    username: str
    password: str


class ScopeSource(BaseModel):
    source_type: str
    url: str
    polling: bool = False
    auth_data: Optional[Union[SSHAuthData, GitHubTokenAuthData]]


class GitScopeSource(ScopeSource):
    SOURCE_TYPE = 'git'
