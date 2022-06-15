from typing import Union

from opal_common.schemas.policy import BaseSchema
from opal_common.schemas.policy_source import GitPolicySource
from pydantic import Field


class Scope(BaseSchema):
    scope_id: str = Field(..., description="Scope ID")
    policy: Union[GitPolicySource]
