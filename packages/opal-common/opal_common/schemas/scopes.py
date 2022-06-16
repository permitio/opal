from typing import Union

from opal_common.schemas.data import DataSourceConfig
from opal_common.schemas.policy import BaseSchema
from opal_common.schemas.policy_source import GitPolicyScopeSource
from pydantic import Field


class Scope(BaseSchema):
    scope_id: str = Field(..., description="Scope ID")
    policy: Union[GitPolicyScopeSource] = Field(..., description="Policy source")
    data: DataSourceConfig = Field(
        DataSourceConfig(entries=[]), description="Data source configuration"
    )
