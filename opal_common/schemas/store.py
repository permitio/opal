from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class StoreTransaction(BaseModel):
    """
    represents a write-op transaction against a policy store
    """
    id: str = Field(..., description="The id of the transaction")
    actions: List[str] = Field(..., description="The write actions performed as part of the transaction")
    success: bool = Field(False, description="Whether or not the transaction was successful")
    error: str = Field("", description="Error message in case of failure, defaults to empty string")

class JSONPatchAction(BaseModel):
    """
    Abstract base class for JSON patch actions (RFC 6902)
    """
    op: str = Field(..., description="patch action to perform")
    path: str = Field(..., description="target location in modified json")
    value: Dict[str, Any] = Field(..., description="json document, the operand of the action")

class ArrayAppendAction(JSONPatchAction):
    op: str = Field("add", description="add action -> adds to the array")
    path: str = Field("-", description="dash marks the last index of an array")