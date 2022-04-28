from pydantic import BaseModel, Field

from opal_common.schemas.data import DataSourceConfig
from opal_common.schemas.sources import PolicySource


class Scope(BaseModel):
    """
    An OPAL scope description.

    An OPAL scope is the policy and the data sources that are supplied
    to OPAL clients, and therefore, loaded to OPA et al.
    """
    scope_id: str = Field(..., description='Scope ID')
    policy: PolicySource = Field(..., description='Policy source configuration')
    data: DataSourceConfig = Field(..., description='Data source configuration')
