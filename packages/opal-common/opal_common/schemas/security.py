from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator

PEER_TYPE_DESCRIPTION = (
    "The peer type we generate access token for, i.e: opal client, data provider, etc."
)
TTL_DESCRIPTION = (
    "Token lifetime (timedelta), can accept duration in seconds or ISO_8601 format."
    + " see: https://en.wikipedia.org/wiki/ISO_8601#Durations"
)
CLAIMS_DESCRIPTION = "extra claims to attach to the jwt"


class PeerType(str, Enum):
    client = "client"
    datasource = "datasource"
    listener = "listener"


class AccessTokenRequest(BaseModel):
    """a request to generate an access token to opal server."""

    id: UUID = Field(default_factory=uuid4)
    type: PeerType = Field(PeerType.client, description=PEER_TYPE_DESCRIPTION)
    ttl: timedelta = Field(timedelta(days=365), description=TTL_DESCRIPTION)
    claims: dict = Field({}, description=CLAIMS_DESCRIPTION)

    @validator("type")
    def force_enum(cls, v):
        if isinstance(v, str):
            return PeerType(v)
        if isinstance(v, PeerType):
            return v
        raise ValueError(f"invalid value: {v}")

    class Config:
        use_enum_values = True
        allow_population_by_field_name = True


class TokenDetails(BaseModel):
    id: UUID
    type: PeerType = Field(PeerType.client, description=PEER_TYPE_DESCRIPTION)
    expired: datetime
    claims: dict


class AccessToken(BaseModel):
    token: str
    type: str = "bearer"
    details: Optional[TokenDetails]
