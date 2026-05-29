"""
Tests for OpenFGA policy store client.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opal_client.policy_store.openfga_client import OpenFGAClient
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.store import StoreTransaction, TransactionType


@pytest.fixture
def client():
    return OpenFGAClient(
        openfga_server_url="http://localhost:8080",
        store_id="test-store-id",
    )


@pytest.fixture
def client_with_token():
    return OpenFGAClient(
        openfga_server_url="http://localhost:8080",
        openfga_auth_token="test-token",
        auth_type=PolicyStoreAuth.TOKEN,
        store_id="test-store-id",
    )


class TestInit:
    def test_default_init(self, client):
        assert client._base_url == "http://localhost:8080"
        assert client._api_url == "http://localhost:8080/api/v1"
        assert client._store_id == "test-store-id"
        assert client._auth_type == PolicyStoreAuth.NONE

    def test_token_init(self, client_with_token):
        assert client_with_token._token == "test-token"
        assert client_with_token._auth_type == PolicyStoreAuth.TOKEN

    def test_oauth_raises(self):
        with pytest.raises(ValueError, match="doesn't support OAuth"):
            OpenFGAClient(
                openfga_server_url="http://localhost:8080",
                auth_type=PolicyStoreAuth.OAUTH,
            )


class TestAuthHeaders:
    def test_no_auth(self, client):
        headers = client._get_auth_headers()
        assert headers == {}

    def test_token_auth(self, client_with_token):
        headers = client_with_token._get_auth_headers()
        assert headers["Authorization"] == "Bearer test-token"


class TestSetPolicy:
    @patch("opal_client.policy_store.openfga_client.aiohttp.ClientSession")
    def test_set_policy_valid_json(self, mock_session, client):
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response

        result = client.set_policy(
            policy_id="test-model",
            policy_code='{"schema_version": "1.1", "type_definitions": []}',
        )

        # Should not raise since it's a coroutine
        assert result is not None

    def test_set_policy_invalid_json(self, client):
        with pytest.raises(ValueError, match="must be valid JSON"):
            client.set_policy(
                policy_id="test-model",
                policy_code="not json",
            )


class TestDataOperations:
    @patch("opal_client.policy_store.openfga_client.aiohttp.ClientSession")
    def test_set_policy_data_with_tuples(self, mock_session, client):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response

        policy_data = [
            {"user": "user:anne", "relation": "viewer", "object": "document:1"}
        ]
        result = client.set_policy_data(policy_data=policy_data)
        assert result is not None

    def test_set_policy_data_invalid_type(self, client):
        with pytest.raises(ValueError, match="must be a dict"):
            client.set_policy_data(policy_data="invalid")


class TestHealth:
    def test_is_ready_initially_false(self, client):
        assert client.is_ready() is False

    def test_is_healthy_initially_false(self, client):
        assert client.is_healthy() is False

    def test_log_transaction_policy_success(self, client):
        transaction = StoreTransaction(
            id="tx1",
            actions=["set_policy"],
            success=True,
            transaction_type=TransactionType.policy,
        )
        client.log_transaction(transaction)
        assert client.is_ready() is False  # data also needed
        assert client.is_healthy() is True
        assert client._had_successful_policy_transaction is True

    def test_log_transaction_data_success(self, client):
        transaction = StoreTransaction(
            id="tx1",
            actions=["set_policy_data"],
            success=True,
            transaction_type=TransactionType.data,
        )
        client.log_transaction(transaction)
        assert client._had_successful_data_transaction is True
