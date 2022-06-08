from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    policy = "policy"
    data = "data"


class RemoteStatus(BaseModel):
    remote_url: str = Field(None, description="Url of remote data/policy source")
    succeed: bool = Field(True, description="Is request succeed")
    error: str = Field(None, description="If failed contains the type of exception")


class StoreTransaction(BaseModel):
    """represents a transaction of policy or data to OPA."""

    id: str = Field(..., description="The id of the transaction")
    actions: List[str] = Field(
        ..., description="The write actions performed as part of the transaction"
    )
    transaction_type: TransactionType = Field(
        None, description="Type of transaction,is it data/policy transaction"
    )
    success: bool = Field(
        False, description="Whether or not the transaction was successful"
    )
    error: str = Field(
        "", description="Error message in case of failure, defaults to empty string"
    )
    creation_time: str = Field(
        None, description="Creation time for this store transaction"
    )
    end_time: str = Field(None, description="Finish time for this store transaction")
    remotes_status: List[RemoteStatus] = Field(
        None,
        description="List of the remote sources for this transaction and their status",
    )


class JSONPatchAction(BaseModel):
    """Abstract base class for JSON patch actions (RFC 6902)"""

    op: str = Field(..., description="patch action to perform")
    path: str = Field(..., description="target location in modified json")
    value: Dict[str, Any] = Field(
        ..., description="json document, the operand of the action"
    )


class ArrayAppendAction(JSONPatchAction):
    op: str = Field("add", description="add action -> adds to the array")
    path: str = Field("-", description="dash marks the last index of an array")
