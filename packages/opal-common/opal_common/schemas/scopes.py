from pydantic import BaseModel, Field

from opal_common.schemas.data import DataSourceConfig
from opal_common.schemas.sources import PolicySource


class ReadOnlyScopeStore(Exception):
    pass


class Scope(BaseModel):
    scope_id: str = Field(..., description='Scope ID')
    policy: PolicySource = Field(..., description='Policy source configuration')
    data: DataSourceConfig = Field(..., description='Data source configuration')
