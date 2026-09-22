from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TransactionType(str, Enum):
    policy = "policy"
    data = "data"


class RemoteStatus(BaseModel):
    remote_url: Optional[str] = Field(
        None, description="Url of remote data/policy source"
    )
    succeed: bool = Field(True, description="Is request succeed")
    error: Optional[str] = Field(
        None, description="If failed contains the type of exception"
    )


class StoreTransaction(BaseModel):
    """Represents a transaction of policy or data to OPA."""

    id: str = Field(..., description="The id of the transaction")
    actions: List[str] = Field(
        ..., description="The write actions performed as part of the transaction"
    )
    transaction_type: Optional[TransactionType] = Field(
        None, description="Type of transaction,is it data/policy transaction"
    )
    success: bool = Field(
        False, description="Whether or not the transaction was successful"
    )
    error: str = Field(
        "", description="Error message in case of failure, defaults to empty string"
    )
    creation_time: Optional[str] = Field(
        None, description="Creation time for this store transaction"
    )
    end_time: Optional[str] = Field(
        None, description="Finish time for this store transaction"
    )
    remotes_status: Optional[List[RemoteStatus]] = Field(
        None,
        description="List of the remote sources for this transaction and their status",
    )


class JSONPatchAction(BaseModel):
    """Abstract base class for JSON patch actions (RFC 6902)"""

    op: str = Field(..., description="patch action to perform")
    path: str = Field(..., description="target location in modified json")
    value: Optional[Any] = Field(
        None, description="json document, the operand of the action"
    )
    from_field: Optional[str] = Field(
        None, description="source location in json", alias="from"
    )

    @model_validator(mode="after")
    def value_must_be_present(self):
        if self.op in ["add", "replace"] and self.value is None:
            # NOTE: pydantic v1 wrapped TypeError from a validator into a
            # ValidationError; pydantic v2 only wraps ValueError/AssertionError
            # and lets TypeError escape. Raise ValueError to keep the caller
            # contract (a ValidationError) identical to v1.
            raise ValueError("'value' must be present when op is either add or replace")
        return self


class ArrayAppendAction(JSONPatchAction):
    op: str = Field("add", description="add action -> adds to the array")
    path: str = Field("-", description="dash marks the last index of an array")
