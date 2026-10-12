from datetime import datetime, timedelta
from enum import Enum
from typing import ClassVar, Optional, Set
from uuid import UUID, uuid4

from opal_common.logging_utils.redaction import RedactedReprMixin
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


DEFAULT_TTL = timedelta(days=365)


def _ttl_wire_schema(schema: dict) -> None:
    """Publish ``ttl`` as the number of seconds it is sent as.

    pydantic 2.14 renders a timedelta field's validation-mode (input) JSON
    schema as an ISO-8601 duration string (default ``"P1Y"``), and
    ``ser_json_timedelta`` keeps only the serialization-mode (output) schema
    a number. Earlier 2.x versions give a number in both modes. FastAPI
    publishes the input schema for the ``/token`` request body
    (``AccessTokenRequest-Input``), so on 2.14 that body read as a string.
    Fixing the schema here keeps the published OpenAPI the same on every
    pydantic version the package admits.
    """
    schema.pop("format", None)
    schema["type"] = "number"
    schema["default"] = DEFAULT_TTL.total_seconds()


class AccessTokenRequest(BaseModel):
    """A request to generate an access token to opal server."""

    id: UUID = Field(default_factory=uuid4)
    type: PeerType = Field(PeerType.client, description=PEER_TYPE_DESCRIPTION)
    ttl: timedelta = Field(
        DEFAULT_TTL, description=TTL_DESCRIPTION, json_schema_extra=_ttl_wire_schema
    )
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


class AccessToken(RedactedReprMixin, BaseModel):
    _redacted_repr_fields: ClassVar[Set[str]] = {"token"}

    token: str
    type: str = "bearer"
    details: Optional[TokenDetails] = None
