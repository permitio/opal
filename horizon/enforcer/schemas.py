from typing import Dict, Any, Optional
from pydantic import BaseModel


class BaseSchema(BaseModel):
    class Config:
        orm_mode = True


class Resource(BaseSchema):
    type: str
    path: str
    instance: str
    context: Dict[str, Any]


class AuthorizationQuery(BaseSchema):
    """
    the format of is_allowed() input
    """
    user: str # user_id or jwt
    action: str
    resource: Resource
    context: Optional[Dict[str, Any]] = {}