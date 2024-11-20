import pytest
import aiohttp
import json
from typing import Dict, Any, List, Tuple

# Constants
FGA_URL = "http://localhost:8080"
STORE_ID = "01JAT34GM6T5WRVMXXDYWGSYKN"

# Test cases
TEST_CASES = [
    # Format: (user, relation, obj, expected_result, description)
    # Positive cases
    ("user:anne", "owner", "document:budget", True, "Anne owns budget document"),
    ("user:beth", "viewer", "document:budget", True, "Beth can view budget document"),
    ("user:charles", "owner", "project:alpha", True, "Charles owns project alpha"),
    ("user:david", "editor", "project:alpha", True, "David can edit project alpha"),
    ("user:emily", "viewer", "document:requirements", True, "Emily can view requirements"),
    ("user:emily", "owner", "document:requirements", True, "Emily owns requirements document"),
    ("user:frank", "owner", "task:write-report", True, "Frank owns write-report task"),
    ("user:george", "assignee", "task:write-report", True, "George is assigned to write-report"),
    ("user:harry", "member", "team:devops", True, "Harry is member of devops team"),

    # Negative cases
    ("user:beth", "owner", "document:budget", False, "Beth should not own budget document"),
    ("user:george", "owner", "task:write-report", False, "George should not own write-report task"),
    ("user:david", "owner", "project:alpha", False, "David should not own project alpha"),
    ("user:frank", "member", "team:devops", False, "Frank should not be member of devops team"),
    ("user:anne", "editor", "project:alpha", False, "Anne should not edit project alpha")
]

# Expected relationships for verification
EXPECTED_RELATIONS = [
    ("user:anne", "owner", "document:budget"),
    ("user:beth", "viewer", "document:budget"),
    ("user:emily", "owner", "document:requirements"),
    ("user:david", "editor", "project:alpha"),
    ("user:harry", "member", "team:devops")
]

# Expected types in authorization model
EXPECTED_TYPES = {"user", "document", "project", "task", "team"}

@pytest.fixture
async def http_client() -> aiohttp.ClientSession:
    """Provides an aiohttp client session"""
    async with aiohttp.ClientSession() as client:
        yield client

class OpenFGAClient:
    """Helper class for OpenFGA API interactions"""

    def __init__(self, client: aiohttp.ClientSession):
        self.client = client

    async def check_permission(self, user: str, relation: str, obj: str) -> Dict[str, Any]:
        """Check a user's permission"""
        url = f"{FGA_URL}/stores/{STORE_ID}/check"
        payload = {
            "tuple_key": {
                "user": user,
                "relation": relation,
                "object": obj
            }
        }

        async with self.client.post(url, json=payload, headers={"Content-Type": "application/json"}) as response:
            response.raise_for_status()
            result = await response.json()
            print(f"\nChecking permission for: {user} {relation} {obj}")
            print(f"Response: {json.dumps(result, indent=2)}")
            return result

    async def get_relationships(self) -> Dict[str, Any]:
        """Get all relationship tuples"""
        url = f"{FGA_URL}/stores/{STORE_ID}/read"
        async with self.client.post(url, json={}, headers={"Content-Type": "application/json"}) as response:
            response.raise_for_status()
            return await response.json()

    async def get_authorization_model(self) -> Dict[str, Any]:
        """Get the current authorization model"""
        url = f"{FGA_URL}/stores/{STORE_ID}/authorization-models"
        async with self.client.get(url, headers={"Content-Type": "application/json"}) as response:
            response.raise_for_status()
            return await response.json()

@pytest.mark.asyncio
class TestOpenFGAPermissions:
    """Test suite for OpenFGA permissions"""

    @pytest.fixture
    async def fga_client(self, http_client: aiohttp.ClientSession) -> OpenFGAClient:
        return OpenFGAClient(http_client)

    @pytest.mark.parametrize("user, relation, obj, expected_result, description", TEST_CASES)
    async def test_permissions(self, fga_client: OpenFGAClient, user: str, relation: str,
                             obj: str, expected_result: bool, description: str):
        """Test permission checks"""
        result = await fga_client.check_permission(user, relation, obj)
        assert result.get("allowed") == expected_result, (
            f"Test failed: {description}\n"
            f"User: {user}, Relation: {relation}, Object: {obj}\n"
            f"Expected: {expected_result}, Got: {result.get('allowed')}"
        )

    async def test_list_relationships(self, fga_client: OpenFGAClient):
        """Test relationship retrieval and verification"""
        result = await fga_client.get_relationships()
        print("\nAll relationships:")
        print(json.dumps(result, indent=2))

        assert "tuples" in result, "No tuples field in response"
        tuples = result["tuples"]
        assert tuples, "No relationships found"

        # Verify expected relationships
        for user, relation, obj in EXPECTED_RELATIONS:
            assert any(
                t["key"]["user"] == user and
                t["key"]["relation"] == relation and
                t["key"]["object"] == obj
                for t in tuples
            ), f"Expected relationship not found: {user} {relation} {obj}"

    async def test_relationship_inheritance(self, fga_client: OpenFGAClient):
        """Test relationship inheritance rules"""
        # Test owner privileges
        owner_tests = [
            ("user:anne", "document:budget"),
            ("user:emily", "document:requirements"),
            ("user:charles", "project:alpha")
        ]

        for user, obj in owner_tests:
            owner_result = await fga_client.check_permission(user, "owner", obj)
            viewer_result = await fga_client.check_permission(user, "viewer", obj)
            assert owner_result.get("allowed"), f"{user} should have owner access to {obj}"
            assert viewer_result.get("allowed"), f"Owner {user} should have viewer access to {obj}"

        # Test editor privileges
        editor_result = await fga_client.check_permission("user:david", "editor", "project:alpha")
        viewer_result = await fga_client.check_permission("user:david", "viewer", "project:alpha")
        assert editor_result.get("allowed"), "Editor should have editor access"
        assert viewer_result.get("allowed"), "Editor should have viewer access"

    async def test_authorization_model(self, fga_client: OpenFGAClient):
        """Test authorization model validation"""
        result = await fga_client.get_authorization_model()
        print("\nAuthorization model:")
        print(json.dumps(result, indent=2))

        assert "authorization_models" in result, "No authorization models found"
        models = result["authorization_models"]
        assert models, "No authorization model configured"

        # Verify latest model types
        latest_model = models[-1]
        type_definitions = latest_model.get("type_definitions", [])
        actual_types = {td["type"] for td in type_definitions}
        assert EXPECTED_TYPES.issubset(actual_types), (
            f"Authorization model missing expected types.\n"
            f"Expected: {EXPECTED_TYPES}\n"
            f"Found: {actual_types}"
        )

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])