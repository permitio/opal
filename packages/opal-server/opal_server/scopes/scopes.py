from pathlib import Path

from pydantic import BaseModel

from opal_server.scopes.sources import ScopeSource


class ScopeConfig(BaseModel):
    scope_id: str
    source: ScopeSource


class ReadOnlyScopeStore(Exception):
    pass


class Scope:
    config: ScopeConfig
    location: Path
    task_id: str
