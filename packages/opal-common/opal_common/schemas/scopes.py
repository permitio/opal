from typing import Union

from opal_common.schemas.data import DataSourceConfig
from opal_common.schemas.policy import BaseSchema
from opal_common.schemas.policy_source import GitPolicyScopeSource
from pydantic import ConfigDict, Field


class Scope(BaseSchema):
    # The top-level model's config decides whether a ValidationError renders
    # the rejected input, so this also covers errors raised inside ``policy``
    # (git auth) and ``data`` (fetcher config) while validating a Scope.
    model_config = ConfigDict(hide_input_in_errors=True)

    scope_id: str = Field(..., description="Scope ID")
    policy: Union[GitPolicyScopeSource] = Field(..., description="Policy source")
    data: DataSourceConfig = Field(
        DataSourceConfig(entries=[]), description="Data source configuration"
    )
