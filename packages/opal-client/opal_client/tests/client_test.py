import pytest
from unittest.mock import patch
from fastapi import status
from fastapi.testclient import TestClient

from opal_client.client import OpalClient
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.config import PolicyStoreTypes


class MockPolicyStoreClient(BasePolicyStoreClient):
    """Mock policy store client for testing."""

    def __init__(self, is_ready_value=True, is_healthy_value=True):
        self._is_ready_value = is_ready_value
        self._is_healthy_value = is_healthy_value

    async def is_ready(self, wait_for_all_data_sources_loaded: bool = False) -> bool:
        return self._is_ready_value

    async def is_healthy(self) -> bool:
        return self._is_healthy_value


@pytest.fixture
def mock_policy_store_ready():
    """Mock policy store that is ready."""
    return MockPolicyStoreClient(is_ready_value=True, is_healthy_value=True)


@pytest.fixture
def mock_policy_store_not_ready():
    """Mock policy store that is not ready."""
    return MockPolicyStoreClient(is_ready_value=False, is_healthy_value=False)


@pytest.fixture
def opal_client_ready(mock_policy_store_ready):
    """Create an OpalClient with a ready policy store."""
    with patch("opal_client.client.PolicyStoreClientFactory.create") as mock_factory:
        mock_factory.return_value = mock_policy_store_ready

        client = OpalClient(
            policy_store_type=PolicyStoreTypes.OPA,
            policy_store=mock_policy_store_ready,
            data_updater=False,  # Disable data updater
            policy_updater=False,  # Disable policy updater
            inline_opa_enabled=False,
            inline_cedar_enabled=False,
        )
        yield client


@pytest.fixture
def opal_client_not_ready(mock_policy_store_not_ready):
    """Create an OpalClient with a policy store that is not ready."""
    with patch("opal_client.client.PolicyStoreClientFactory.create") as mock_factory:
        mock_factory.return_value = mock_policy_store_not_ready

        client = OpalClient(
            policy_store_type=PolicyStoreTypes.OPA,
            policy_store=mock_policy_store_not_ready,
            data_updater=False,  # Disable data updater
            policy_updater=False,  # Disable policy updater
            inline_opa_enabled=False,
            inline_cedar_enabled=False,
        )
        yield client


@pytest.fixture
def test_client_ready(opal_client_ready):
    """Create a FastAPI test client with a ready OPAL client."""
    return TestClient(opal_client_ready.app)


@pytest.fixture
def test_client_not_ready(opal_client_not_ready):
    """Create a FastAPI test client with a not ready OPAL client."""
    return TestClient(opal_client_not_ready.app)


def test_ready_endpoint_when_ready(test_client_ready, opal_client_ready):
    """Test that /ready endpoint returns 200 when policy store is ready and _is_ready is called with correct arguments."""
    with patch.object(
        opal_client_ready, "_is_ready", return_value=True
    ) as mock_is_ready:
        response = test_client_ready.get("/ready")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}
        mock_is_ready.assert_called_once_with(wait_for_all_data_sources_loaded=False)


def test_ready_endpoint_when_not_ready(test_client_not_ready, opal_client_not_ready):
    """Test that /ready endpoint returns 503 when policy store is not ready and _is_ready is called with correct arguments."""
    with patch.object(
        opal_client_not_ready, "_is_ready", return_value=False
    ) as mock_is_ready:
        response = test_client_not_ready.get("/ready")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json() == {"status": "unavailable"}
        mock_is_ready.assert_called_once_with(wait_for_all_data_sources_loaded=False)


def test_ready_endpoint_with_query_parameter_true(test_client_ready, opal_client_ready):
    """Test that /ready endpoint works with wait_for_all_data_sources_loaded parameter and _is_ready is called with correct arguments."""
    with patch.object(
        opal_client_ready, "_is_ready", return_value=True
    ) as mock_is_ready:
        response = test_client_ready.get("/ready?wait_for_all_data_sources_loaded=true")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}
        mock_is_ready.assert_called_once_with(wait_for_all_data_sources_loaded=True)


def test_ready_endpoint_with_query_parameter_false(
    test_client_ready, opal_client_ready
):
    """Test that /ready endpoint works with wait_for_all_data_sources_loaded=false and _is_ready is called with correct arguments."""
    with patch.object(
        opal_client_ready, "_is_ready", return_value=True
    ) as mock_is_ready:
        response = test_client_ready.get(
            "/ready?wait_for_all_data_sources_loaded=false"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}
        mock_is_ready.assert_called_once_with(wait_for_all_data_sources_loaded=False)
