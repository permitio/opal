from typing import Dict, Any, List, Optional

from fastapi import APIRouter, status, HTTPException
from starlette.status import HTTP_404_NOT_FOUND
from opal_client.local.schemas import Message, SyncedRole, SyncedUser
from opal_client.policy_store import BasePolicyStoreClient, DEFAULT_POLICY_STORE
from opal_client.logger import logger


def init_local_cache_api_router(policy_store:BasePolicyStoreClient=DEFAULT_POLICY_STORE):
    router = APIRouter()

    def error_message(msg: str):
        return {
            "model": Message,
            "description": msg,
        }

    async def get_data_for_synced_user(user_id: str) -> Dict[str, Any]:
        response = await policy_store.get_data(f"/user_roles/{user_id}")
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
            metadata=result.get("metadata", {}),
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
        response = await policy_store.get_data(f"/user_roles")
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
                    metadata=user_data.get("metadata", {}),
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
        # will issue an opa request to get cached user data
        result = await get_data_for_synced_user(user_id)
        # will issue *another* opa request to list all roles, not just the roles for this user
        cached_roles: List[SyncedRole] = await list_roles()
        role_data = {role.id: role for role in cached_roles }

        raw_roles=result.get("roles", [])

        roles = []
        for r in raw_roles:
            role_id = r.get("id")
            roles.append(
                SyncedRole(
                    id=role_id,
                    name=r.get("name"),
                    org_id=r.get("scope", {}).get("org", None),
                    metadata=role_data.get(role_id, {}).metadata,
                    permissions=role_data.get(role_id, {}).permissions,
                )
            )
        return roles

    @router.get(
        "/users/{user_id}/organizations",
        response_model=List[str],
        responses={
            404: error_message("User not found (i.e: not synced to Authorization service)"),
        }
    )
    async def get_user_orgs(user_id: str):
        """
        Get orgs **assigned to user** directly from OPA cache.
        This endpoint only returns orgs that the user **has an assigned role in**.
        i.e: if the user is assigned to org "org1" but has no roles in that org,
        "org1" will not be returned by this endpoint.

        If user does not exist in OPA cache (i.e: not synced), returns 404.
        """
        result = await get_data_for_synced_user(user_id)
        roles = result.get("roles", [])
        orgs = [r.get("scope", {}).get("org", None) for r in roles]
        orgs = [org for org in orgs if org is not None]
        return orgs

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
        response = await policy_store.get_data(f"/role_permissions")
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
                    metadata=role_data.get("metadata", {}),
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
        response = await policy_store.get_data(f"/role_permissions/{role_id}")
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
            metadata=role_data.get("metadata", {}),
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
        response = await policy_store.get_data(f"/role_permissions")
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
                metadata=role_data.get("metadata", {}),
                permissions=permissions
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No such role in OPA cache!"
        )
    return router