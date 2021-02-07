from typing import Dict, Any, List, Optional

from fastapi import APIRouter, status, HTTPException
from starlette.status import HTTP_404_NOT_FOUND
from horizon.local.schemas import Message, SyncedRole, SyncedUser
from horizon.enforcer.client import opa
from horizon.logger import get_logger

logger = get_logger("Local API")
router = APIRouter()

def error_message(msg: str):
    return {
        "model": Message,
        "description": msg,
    }

async def get_data_for_synced_user(user_id: str) -> Dict[str, Any]:
    response = await opa.get_data(f"/user_roles/{user_id}")
    result = response.get("result", None)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user with id '{user_id}' was not found in OPA cache! (not synced)"
        )
    return result

def permission_shortname(permission: Dict[str, Any]) -> Optional[str]:
    resource = permission.get("resource", {}).get("type", None)
    action = permission.get("action", None)

    if resource is None or action is None:
        return None
    return f"{resource}:{action}"


@router.get(
    "/users/{user_id}",
    response_model=SyncedUser,
    responses={
        404: error_message("User not found (i.e: not synced to Authorization service)"),
    }
)
async def get_user(user_id: str):
    """
    Get user data directly from OPA cache.

    If user does not exist in OPA cache (i.e: not synced), returns 404.
    """
    result = await get_data_for_synced_user(user_id)
    roles=result.get("roles", [])
    roles=[
        SyncedRole(
            id=r.get("id"),
            name=r.get("name"),
            org_id=r.get("scope", {}).get("org", None),
        )
        for r in roles
    ]
    user = SyncedUser(
        id=user_id,
        email=result.get("email", None),
        name=result.get("name", None),
        roles=roles,
    )
    return user

@router.get(
    "/users",
    response_model=List[SyncedUser],
    responses={
        404: error_message("OPA has no users stored in cache"),
    }
)
async def list_users():
    """
    Get all users stored in OPA cache.

    Be advised, if you have many (i.e: few hundreds or more) users this query might be expensive latency-wise.
    """
    response = await opa.get_data(f"/user_roles")
    result = response.get("result", None)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OPA has no users stored in cache! Did you synced users yet via the sdk or the cloud console?"
        )
    users = []
    for user_id, user_data in iter(result.items()):
        roles=user_data.get("roles", [])
        roles=[
            SyncedRole(
                id=r.get("id"),
                name=r.get("name"),
                org_id=r.get("scope", {}).get("org", None),
            )
            for r in roles
        ]
        users.append(
            SyncedUser(
                id=user_id,
                email=user_data.get("email", None),
                name=user_data.get("name", None),
                roles=roles,
            )
        )
    return users

@router.get(
    "/users/{user_id}/roles",
    response_model=List[SyncedRole],
    responses={
        404: error_message("User not found (i.e: not synced to Authorization service)"),
    }
)
async def get_user_roles(user_id: str):
    """
    Get roles **assigned to user** directly from OPA cache.

    If user does not exist in OPA cache (i.e: not synced), returns 404.
    """
    result = await get_data_for_synced_user(user_id)
    roles=result.get("roles", [])
    roles=[
        SyncedRole(
            id=r.get("id"),
            name=r.get("name"),
            org_id=r.get("scope", {}).get("org", None),
        )
        for r in roles
    ]
    return roles

@router.get(
    "/roles",
    response_model=List[SyncedRole],
    responses={
        404: error_message("OPA has no roles stored in cache"),
    }
)
async def list_roles():
    """
    Get all roles stored in OPA cache.
    """
    response = await opa.get_data(f"/role_permissions")
    result = response.get("result", None)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OPA has no roles stored in cache! Did you define roles yet via the sdk or the cloud console?"
        )
    roles = []
    for role_id, role_data in iter(result.items()):
        permissions = [permission_shortname(p) for p in role_data.get("permissions", [])]
        permissions = [p for p in permissions if p is not None]
        roles.append(
            SyncedRole(
                id=role_id,
                name=role_data.get("name"),
                permissions=permissions
            )
        )
    return roles

@router.get(
    "/roles/{role_id}",
    response_model=SyncedRole,
    responses={
        404: error_message("Role not found"),
    }
)
async def get_role_by_id(role_id: str):
    """
    Get role (by the role id) directly from OPA cache.

    If role is not found, returns 404.
    Possible reasons are either:

    - role was never created via SDK or via the cloud console.
    - role was (very) recently created and the policy update did not propagate yet.
    """
    response = await opa.get_data(f"/role_permissions/{role_id}")
    role_data = response.get("result", None)
    if role_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No such role in OPA cache!"
        )
    permissions = [permission_shortname(p) for p in role_data.get("permissions", [])]
    permissions = [p for p in permissions if p is not None]
    role = SyncedRole(
        id=role_id,
        name=role_data.get("name"),
        permissions=permissions
    )
    return role

@router.get(
    "/roles/by-name/{role_name}",
    response_model=SyncedRole,
    responses={
        404: error_message("Role not found"),
    }
)
async def get_role_by_name(role_name: str):
    """
    Get role (by the role name - case sensitive) directly from OPA cache.

    If role is not found, returns 404.
    Possible reasons are either:

    - role with such name was never created via SDK or via the cloud console.
    - role was (very) recently created and the policy update did not propagate yet.
    """
    response = await opa.get_data(f"/role_permissions")
    result = response.get("result", None)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OPA has no roles stored in cache!"
        )
    for role_id, role_data in iter(result.items()):
        name = role_data.get("name")
        if name is None or name != role_name:
            continue
        permissions = [permission_shortname(p) for p in role_data.get("permissions", [])]
        permissions = [p for p in permissions if p is not None]
        return SyncedRole(
            id=role_id,
            name=name,
            permissions=permissions
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No such role in OPA cache!"
    )