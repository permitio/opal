from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    """A request to generate an access token to opal server."""

    id: UUID = Field(default_factory=uuid4)
    type: PeerType = Field(PeerType.client, description=PEER_TYPE_DESCRIPTION)
    ttl: timedelta = Field(timedelta(days=365), description=TTL_DESCRIPTION)
    claims: dict = Field({}, description=CLAIMS_DESCRIPTION)

    # ``ser_json_timedelta="float"`` keeps ``ttl`` on the wire as float seconds,
    # the way pydantic v1 sent it. v2 defaults to an ISO-8601 duration and
    # collapses 365 days - the CLI default, and now the published OpenAPI
    # default - to "P1Y", which a v1 duration parser cannot read (it has no year
    # group). Without this, `opal-client obtain-token` from an upgraded CLI 422s
    # against a server that has not restarted yet. The reverse direction is
    # safe: v2 still accepts the float form.
    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        ser_json_timedelta="float",
    )

    @field_validator("type")
    @classmethod
    def force_enum(cls, v):
        if isinstance(v, str):
            return PeerType(v)
        if isinstance(v, PeerType):
            return v
        raise ValueError(f"invalid value: {v}")


class TokenDetails(BaseModel):
    id: UUID
    type: PeerType = Field(PeerType.client, description=PEER_TYPE_DESCRIPTION)
    expired: datetime
    claims: dict


class AccessToken(BaseModel):
    token: str
    type: str = "bearer"
    details: Optional[TokenDetails] = None
