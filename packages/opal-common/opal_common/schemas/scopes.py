from typing import Union

from pydantic import Field

from opal_common.schemas.policy import BaseSchema
from opal_common.schemas.policy_source import GitPolicySource


class Scope(BaseSchema):
    scope_id: str = Field(..., description="Scope ID")
    policy: Union[GitPolicySource]
