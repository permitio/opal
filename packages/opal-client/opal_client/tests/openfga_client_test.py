import pytest
from aiohttp import ClientSession, ClientError
from opal_client.policy_store.openfga_client import OpenFGAClient
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.store import StoreTransaction, TransactionType

@pytest.fixture 
def mock_response():
    class MockResponse:
        def __init__(self, status=200, data=None):
            self.status = status
            self._data = data or {}

        async def json(self):
            return self._data

        async def text(self):
            return str(self._data)

        async def __aenter__(self):
            return self
            
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    return MockResponse

@pytest.fixture
def mock_session(mocker, mock_response):
    """Create a mocked aiohttp ClientSession with default success response"""
    mock = mocker.patch('aiohttp.ClientSession', autospec=True)
    session = mock.return_value
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None

    # Create a default mock response
    default_response = mock_response(status=200, data={})
    session.post.return_value.__aenter__.return_value = default_response
    session.get.return_value.__aenter__.return_value = default_response

    return session

@pytest.fixture
def openfga_client(mock_session):
    return OpenFGAClient(
        openfga_server_url="http://localhost:8080",
        store_id="test-store",
        auth_type=PolicyStoreAuth.NONE
    )

def test_constructor_with_token_auth():
    """Test successful token auth initialization"""
    client = OpenFGAClient(
        openfga_server_url="http://example.com",
        openfga_auth_token="test-token", 
        auth_type=PolicyStoreAuth.TOKEN
    )
    assert client._token == "test-token"
    assert client._auth_type == PolicyStoreAuth.TOKEN

def test_constructor_fails_with_token_auth_missing_token():
    """Test that client fails with token auth but no token provided"""
    with pytest.raises(Exception, match="Required variables for token auth are not set"):
        OpenFGAClient(
            openfga_server_url="http://example.com",
            auth_type=PolicyStoreAuth.TOKEN
        )

def test_constructor_with_invalid_oauth():
    """Test that client fails with invalid OAuth configuration"""
    with pytest.raises(ValueError, match="OpenFGA doesn't support OAuth"):
        OpenFGAClient(
            openfga_server_url="http://example.com",
            auth_type=PolicyStoreAuth.OAUTH
        )

@pytest.mark.asyncio
async def test_set_policy_success(openfga_client, mock_session, mock_response):
    """Test successful policy creation"""
    response = mock_response(
        status=201,
        data={"authorization_model_id": "test-id"}
    )
    mock_session.post.return_value.__aenter__.return_value = response

    result = await openfga_client.set_policy(
        policy_id="test-model",
        policy_code='{"schema_version":"1.1"}'
    )
    
    assert result["authorization_model_id"] == "test-id"
    assert openfga_client._policy_version == "test-id"
    
    # Verify correct endpoint and payload
    mock_session.post.assert_called_once()
    args = mock_session.post.call_args
    assert "/authorization-models" in args[0][0]
    assert "schema_version" in args[1]["json"]

@pytest.mark.asyncio
async def test_set_policy_failure(openfga_client, mock_session, mock_response):
    """Test handling of policy creation failure"""
    response = mock_response(
        status=400,
        data={"code": "invalid_schema", "message": "Invalid schema"}
    )
    mock_session.post.return_value.__aenter__.return_value = response

    # Override retry config for this test to avoid long waits
    from tenacity import stop_after_attempt
    openfga_client.set_policy.retry.stop = stop_after_attempt(1)

    with pytest.raises(Exception) as exc_info:
        await openfga_client.set_policy(
            policy_id="test-model",
            policy_code='{"invalid": "schema"}'
        )
    assert "Failed to set policy: HTTP 400" in str(exc_info.value)



@pytest.mark.asyncio
async def test_set_policy_data_success(openfga_client, mock_session, mock_response):
    """Test successful relationship tuple creation"""
    response = mock_response(status=200)
    mock_session.post.return_value.__aenter__.return_value = response

    test_tuple = {
        "user": "user:anne",
        "relation": "reader", 
        "object": "document:budget"
    }

    await openfga_client.set_policy_data([test_tuple])

    # Verify correct write request format
    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args[1]
    assert "writes" in call_kwargs["json"]
    assert len(call_kwargs["json"]["writes"]["tuple_keys"]) == 1
    assert call_kwargs["json"]["writes"]["tuple_keys"][0] == test_tuple

@pytest.mark.asyncio
async def test_get_data_with_input_success(openfga_client, mock_session, mock_response):
    """Test successful check authorization request"""
    response = mock_response(
        status=200,
        data={"allowed": True, "resolution": "direct"}
    )
    mock_session.post.return_value.__aenter__.return_value = response

    class TestInput:
        def dict(self):
            return {
                "user": "user:anne",
                "relation": "reader",
                "object": "document:budget",
                "context": {"time": "business_hours"}
            }

    result = await openfga_client.get_data_with_input(
        path="document:budget",
        input_model=TestInput()
    )

    assert result["allowed"] is True 
    assert result["resolution"] == "direct"

    # Verify check request format
    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args[1]
    assert "tuple_key" in call_kwargs["json"]
    assert "context" in call_kwargs["json"]

@pytest.mark.asyncio
async def test_retry_behavior(openfga_client, mock_session, mock_response):
    """Test retry logic on temporary failures"""
    # Set up responses for retries
    error_response = mock_response(status=500, data={"error": "Server Error"})
    success_response = mock_response(status=200)

    mock_session.post.return_value.__aenter__.side_effect = [
        error_response,
        error_response, 
        success_response
    ]

    await openfga_client.set_policy_data([{
        "user": "user:anne",
        "relation": "reader",
        "object": "document:budget"
    }])

    assert mock_session.post.call_count == 3


@pytest.mark.asyncio
async def test_network_error_handling(openfga_client, mock_session):
    """Test handling of network errors"""
    mock_session.post.side_effect = ClientError()
    
    with pytest.raises(Exception):
        await openfga_client.set_policy_data([{
            "user": "user:anne",
            "relation": "reader",
            "object": "document:budget"
        }])

@pytest.mark.asyncio
async def test_set_policy_failure(openfga_client, mock_session, mock_response):
    """Test handling of policy creation failure"""
    response = mock_response(
        status=400,
        data={"code": "invalid_schema", "message": "Invalid schema"}
    )
    mock_session.post.return_value.__aenter__.return_value = response

    # Modify retry config to make test faster
    import tenacity
    openfga_client.set_policy.retry.stop = tenacity.stop_after_attempt(1)
    
    with pytest.raises(tenacity.RetryError) as exc_info:
        await openfga_client.set_policy(
            policy_id="test-model",
            policy_code='{"invalid": "schema"}'
        )
    # Verify inner exception details
    assert isinstance(exc_info.value.last_attempt.exception(), Exception)
    assert "Failed to set policy: HTTP 400" in str(exc_info.value.last_attempt.exception())

@pytest.mark.asyncio
async def test_log_transaction(openfga_client):
    """Test transaction logging and health check state"""
    # Set initial success transactions
    policy_transaction = StoreTransaction(
        id="test-1",
        actions=["set_policy"],
        success=True,
        transaction_type=TransactionType.policy
    )
    await openfga_client.log_transaction(policy_transaction)

    data_transaction = StoreTransaction(
        id="test-2",
        actions=["set_policy_data"],
        success=True,
        transaction_type=TransactionType.data
    )
    await openfga_client.log_transaction(data_transaction)

    # Should be healthy after successful transactions
    assert await openfga_client.is_healthy()

    # Apply failed transaction
    failed_transaction = StoreTransaction(
        id="test-3",
        actions=["set_policy_data"],
        success=False,
        error="Test failure",
        transaction_type=TransactionType.data
    )
    await openfga_client.log_transaction(failed_transaction)

    # Should be unhealthy after failure
    assert not await openfga_client.is_healthy()

    # Restore healthy state with new success
    recovery_transaction = StoreTransaction(
        id="test-4",
        actions=["set_policy_data"],
        success=True,
        transaction_type=TransactionType.data
    )
    await openfga_client.log_transaction(recovery_transaction)
    assert await openfga_client.is_healthy()

@pytest.mark.asyncio 
async def test_health_check_states(openfga_client):
    """Test various health check states"""
    # Initially neither ready nor healthy - no transactions yet
    initial_health = await openfga_client.is_healthy()
    initial_ready = await openfga_client.is_ready() 
    assert not initial_ready
    assert not initial_health

    # Enable both policy and data updaters for complete testing
    openfga_client._transaction_state._policy_updater_disabled = False
    openfga_client._transaction_state._data_updater_disabled = False

    # Add successful policy transaction
    policy_tx = StoreTransaction(
        id="p1",
        actions=["set_policy"],
        success=True,
        transaction_type=TransactionType.policy,
    )
    await openfga_client.log_transaction(policy_tx)

    # Should be not yet ready or healthy - need data transaction too
    assert not await openfga_client.is_ready()
    assert not await openfga_client.is_healthy()

    # Add successful data transaction
    data_tx = StoreTransaction(
        id="d1",
        actions=["set_policy_data"],
        success=True,
        transaction_type=TransactionType.data,
    )
    await openfga_client.log_transaction(data_tx)

    # Now should be both ready and healthy
    assert await openfga_client.is_ready()
    assert await openfga_client.is_healthy()

    # Test failed policy transaction
    failed_policy = StoreTransaction(
        id="p2",
        actions=["set_policy"],
        success=False,
        transaction_type=TransactionType.policy,
    )
    await openfga_client.log_transaction(failed_policy)

    # Should become unhealthy but remain ready
    assert await openfga_client.is_ready()
    assert not await openfga_client.is_healthy()

    # Test disabled updaters
    openfga_client._transaction_state._policy_updater_disabled = True
    openfga_client._transaction_state._data_updater_disabled = True

    # Should be both ready and healthy when updaters are disabled
    assert await openfga_client.is_ready()
    assert await openfga_client.is_healthy()