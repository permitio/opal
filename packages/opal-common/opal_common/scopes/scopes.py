from pydantic import BaseModel

from opal_common.scopes.sources import PolicySource


class ScopeConfig(BaseModel):
    scope_id: str
    policy: PolicySource


class ReadOnlyScopeStore(Exception):
    pass


class Scope(BaseModel):
    config: ScopeConfig
