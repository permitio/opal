from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PolicyStoreTypes(Enum):
    OPA = "OPA"
    CEDAR = "CEDAR"
    MOCK = "MOCK"


class PolicyStoreAuth(Enum):
    NONE = "none"
    TOKEN = "token"
    OAUTH = "oauth"
    TLS = "tls"


class PolicyStoreDetails(BaseModel):
    """
    represents a policy store endpoint - contains the policy store's:
    - location (url)
    - type
    - credentials
    """

    type: PolicyStoreTypes = Field(
        PolicyStoreTypes.OPA,
        description="the type of policy store, currently only OPA is officially supported",
    )
    url: str = Field(
        ...,
        description="the url that OPA can be found in. if localhost is the host - "
        "it means OPA is on the same hostname as OPAL client.",
    )
    token: Optional[str] = Field(
        None, description="optional access token required by the policy store"
    )

    auth_type: PolicyStoreAuth = Field(
        PolicyStoreAuth.NONE,
        description="the type of authentication is supported for the policy store.",
    )

    oauth_client_id: Optional[str] = Field(
        None, description="optional OAuth client id required by the policy store"
    )
    oauth_client_secret: Optional[str] = Field(
        None, description="optional OAuth client secret required by the policy store"
    )
    oauth_server: Optional[str] = Field(
        None, description="optional OAuth server required by the policy store"
    )

    @field_validator("type")
    @classmethod
    def force_enum(cls, v):
        if isinstance(v, str):
            return PolicyStoreTypes(v)
        if isinstance(v, PolicyStoreTypes):
            return v
        raise ValueError(f"invalid value: {v}")

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)
