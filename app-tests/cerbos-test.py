import json
from typing import Any, Dict, List

import aiohttp
import pytest

# Constants
CERBOS_URL = "http://localhost:3592"

# Test cases, mirroring the "User Role" / "Admin Role" suites from
# cerbos/example-cerbos-policy-repository's basicResource_test.yaml.
# Format: (principal_id, roles, resource_id, attrs, action, expected_allow, description)
RESOURCES = {
    "resource1": {"ownerId": "sally", "isPublished": True},
    "resource2": {"ownerId": "sally", "isPublished": True},
    "resource3": {"ownerId": "sally", "isPublished": False},
}

TEST_CASES = [
    # Admin can do everything
    (
        "ian",
        ["ADMIN"],
        "resource1",
        RESOURCES["resource1"],
        "read",
        True,
        "Admin can read",
    ),
    (
        "ian",
        ["ADMIN"],
        "resource1",
        RESOURCES["resource1"],
        "update",
        True,
        "Admin can update",
    ),
    (
        "ian",
        ["ADMIN"],
        "resource3",
        RESOURCES["resource3"],
        "delete",
        True,
        "Admin can delete unpublished",
    ),
    # Owner (sally) can do everything to her own resources
    (
        "sally",
        ["USER"],
        "resource1",
        RESOURCES["resource1"],
        "read",
        True,
        "Owner can read",
    ),
    (
        "sally",
        ["USER"],
        "resource1",
        RESOURCES["resource1"],
        "update",
        True,
        "Owner can update",
    ),
    (
        "sally",
        ["USER"],
        "resource3",
        RESOURCES["resource3"],
        "delete",
        True,
        "Owner can delete unpublished own resource",
    ),
    # Non-owner (frank) can read published resources but not modify them
    (
        "frank",
        ["USER"],
        "resource1",
        RESOURCES["resource1"],
        "read",
        True,
        "Non-owner can read published resource",
    ),
    (
        "frank",
        ["USER"],
        "resource1",
        RESOURCES["resource1"],
        "update",
        False,
        "Non-owner cannot update",
    ),
    (
        "frank",
        ["USER"],
        "resource1",
        RESOURCES["resource1"],
        "delete",
        False,
        "Non-owner cannot delete",
    ),
    # Non-owner cannot even read unpublished resources
    (
        "frank",
        ["USER"],
        "resource3",
        RESOURCES["resource3"],
        "read",
        False,
        "Non-owner cannot read unpublished resource",
    ),
]


@pytest.fixture
async def http_client() -> aiohttp.ClientSession:
    async with aiohttp.ClientSession() as client:
        yield client


class CerbosApiClient:
    """Helper class for Cerbos check API interactions."""

    def __init__(self, client: aiohttp.ClientSession):
        self.client = client

    async def check(
        self,
        principal_id: str,
        roles: List[str],
        resource_id: str,
        resource_kind: str,
        attrs: Dict[str, Any],
        actions: List[str],
    ) -> Dict[str, Any]:
        url = f"{CERBOS_URL}/api/check/resources"
        payload = {
            "principal": {"id": principal_id, "roles": roles},
            "resources": [
                {
                    "resource": {
                        "id": resource_id,
                        "kind": resource_kind,
                        "attr": attrs,
                    },
                    "actions": actions,
                }
            ],
        }
        async with self.client.post(url, json=payload) as response:
            response.raise_for_status()
            result = await response.json()
            print(f"\nCheck: {principal_id} {actions} {resource_id}")
            print(f"Response: {json.dumps(result, indent=2)}")
            return result


class TestCerbosPermissions:
    """Test suite for Cerbos permissions, against the real basicResource policy
    from cerbos/example-cerbos-policy-repository."""

    @pytest.fixture
    async def cerbos_client(
        self, http_client: aiohttp.ClientSession
    ) -> CerbosApiClient:
        return CerbosApiClient(http_client)

    @pytest.mark.parametrize(
        "principal_id, roles, resource_id, attrs, action, expected_allow, description",
        TEST_CASES,
    )
    async def test_permissions(
        self,
        cerbos_client: CerbosApiClient,
        principal_id: str,
        roles: List[str],
        resource_id: str,
        attrs: Dict[str, Any],
        action: str,
        expected_allow: bool,
        description: str,
    ):
        result = await cerbos_client.check(
            principal_id, roles, resource_id, "basicResource", attrs, [action]
        )
        actions = result["results"][0]["actions"]
        expected_effect = "EFFECT_ALLOW" if expected_allow else "EFFECT_DENY"
        assert actions.get(action) == expected_effect, (
            f"Test failed: {description}\n"
            f"Principal: {principal_id}, Action: {action}, Resource: {resource_id}\n"
            f"Expected: {expected_effect}, Got: {actions.get(action)}"
        )

    async def test_policy_synced(self, http_client: aiohttp.ClientSession):
        """Confirms OPAL actually pushed the real policy (not just that the
        Cerbos PDP is up) - fails loudly if the policy sync silently no-op'd."""
        async with http_client.get(
            f"{CERBOS_URL}/admin/policies",
            auth=aiohttp.BasicAuth("cerbos", "cerbosAdmin"),
        ) as response:
            response.raise_for_status()
            result = await response.json()
            print("\nSynced policies:", result)
            assert result.get(
                "policyIds"
            ), "No policies found in Cerbos - sync did not happen"
