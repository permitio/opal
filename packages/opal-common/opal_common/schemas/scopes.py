from pydantic import Field

from opal_common.schemas.policy import BaseSchema
from opal_common.schemas.policy_source import PolicySource


class Scope(BaseSchema):
    scope_id: str = Field(..., description="Scope ID")
    policy: PolicySource
