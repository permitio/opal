from enum import Enum
from typing import Union

from opal_common.schemas.policy import BaseSchema
from pydantic import Field


class SecretTypeEnum(str, Enum):
    """is the passed secret in the webhook a token or a signature on the
    request body."""

    token = "token"
    signature = "signature"


class GitWebhookRequestParams(BaseSchema):
    secret_header_name: str = Field(
        ...,
        description="The HTTP header holding the secret",
    )
    secret_type: SecretTypeEnum = Field(
        ...,
        description=SecretTypeEnum.__doc__,
    )
    secret_parsing_regex: str = Field(
        ...,
        description="The regex used to parse out the actual signature from the header. Use '(.*)' for the entire value",
    )
    event_header_name: str = Field(
        ...,
        description="The HTTP header holding the event",
    )
    push_event_value: str = Field(
        ...,
        description="The event value indicating a Git push",
    )
