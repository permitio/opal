from pydantic import BaseModel

from opal_common.schemas.data import DataSourceConfig
from opal_common.scopes.sources import PolicySource


class ReadOnlyScopeStore(Exception):
    pass


class Scope(BaseModel):
    scope_id: str
    policy: PolicySource
    data: DataSourceConfig
