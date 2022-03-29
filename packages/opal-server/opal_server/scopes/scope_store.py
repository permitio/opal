from pathlib import Path

from pygit2 import Repository

from opal_server.scopes.pull_engine import PullEngine
from opal_server.scopes.scopes import ScopeConfig, Scope


class ScopeNotFound(Exception):
    pass


class ScopeStore:
    def __init__(self, base_dir: str, fetch_engine: PullEngine):
        self.base_dir = Path(base_dir)
        self.engine = fetch_engine
        self.scopes: dict[str, Scope] = {}

    def add_scope(self, scope_config: ScopeConfig):
        repo_path = self.base_dir/scope_config.scope_id
        repo: Repository

        task_id = self._fetch_scope_from_source(scope_config)

        scope = Scope()
        scope.config = scope_config
        scope.location = repo_path
        scope.task_id = task_id
        self.scopes[scope_config.scope_id] = scope

        return scope

    def get_scope(self, scope_id: str) -> Scope:
        if scope_id in self.scopes.keys():
            return self.scopes[scope_id]
        raise ScopeNotFound()

    def update_scope(self, scope_id: str):
        pass

    def delete_scope(self, scope_id: str):
        pass

    def _fetch_scope_from_source(self, scope: ScopeConfig):
        return self.engine.fetch_source(self.base_dir, scope)
