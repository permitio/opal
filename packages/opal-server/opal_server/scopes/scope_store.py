from pathlib import Path
from typing import Optional

import pygit2
from pydantic import BaseModel
from pygit2 import Repository


class PolicySourceAuthData(BaseModel):
    pass


class SSHAuthData(PolicySourceAuthData):
    username: str
    public_key: str
    private_key: str


class PolicySource(BaseModel):
    source_type: str
    url: str
    auth_data: Optional[PolicySourceAuthData]


class ScopeConfig(BaseModel):
    scope_id: str
    policy: PolicySource


class ScopeNotFound(Exception):
    pass


class ReadOnlyScopeStore(Exception):
    pass


class Scope:
    config: ScopeConfig
    repository: Repository


class ScopeStore:
    def __init__(self, base_dir: str, writer=False):
        self.base_dir = Path(base_dir)
        self.writer = writer
        self.scopes = {}

    def add_scope(self, scope_config: ScopeConfig):
        repo_path = self.base_dir/scope_config.scope_id
        repo: Repository

        if pygit2.discover_repository(str(repo_path)) is None:
            repo = pygit2.clone_repository(scope_config.policy.url, str(self.base_dir/scope_config.scope_id))
        else:
            repo = Repository(repo_path)

        scope = Scope()
        scope.config = scope_config
        scope.repository = repo
        self.scopes[scope_config.scope_id] = scope

    def get_scope(self, scope_id: str) -> Scope:
        if scope_id in self.scopes.keys():
            return self.scopes[scope_id]
        raise ScopeNotFound()

    def update_scope(self, scope_id: str):
        pass

    def delete_scope(self, scope_id: str):
        pass
