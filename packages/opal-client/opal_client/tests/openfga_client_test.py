import pytest
from aiohttp import ClientSession, ClientError, ClientResponseError
from opal_client.policy_store.openfga_client import OpenFGAClient
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.store import StoreTransaction, TransactionType
import aiohttp
from tenacity import RetryError, stop_after_attempt

@pytest.fixture 
def mock_response():
    class MockResponse:
        def __init__(self, status=200, data=None):
            self.status = status
            self._data = data or {}

        def raise_for_status(self):
            if self.status >= 400:
                raise aiohttp.ClientResponseError(
                    request_info=None,
                    history=None,
                    status=self.status,
                    message=str(self._data)
                )

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
    mock = mocker.patch('aiohttp.ClientSession', autospec=True)
    session = mock.return_value
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None

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

def test_constructor_with_valid_token_auth():
    client = OpenFGAClient(
        openfga_server_url="http://example.com",
        openfga_auth_token="test-token", 
        auth_type=PolicyStoreAuth.TOKEN
    )
    assert client._token == "test-token"
    assert client._auth_type == PolicyStoreAuth.TOKEN

def test_constructor_fails_with_token_auth_missing_token():
    with pytest.raises(ValueError, match="Authentication token required when using TOKEN auth type"):
        OpenFGAClient(
            openfga_server_url="http://example.com",
            auth_type=PolicyStoreAuth.TOKEN
        )

def test_constructor_fails_with_oauth():
    with pytest.raises(ValueError, match="OpenFGA doesn't support OAuth authentication"):
        OpenFGAClient(
            openfga_server_url="http://example.com",
            auth_type=PolicyStoreAuth.OAUTH
        )

@pytest.mark.asyncio
async def test_set_policy_success(openfga_client, mock_session, mock_response):
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
    mock_session.post.assert_called_once()

@pytest.mark.asyncio
async def test_set_policy_data_success(openfga_client, mock_session, mock_response):
    response = mock_response(status=200)
    mock_session.post.return_value.__aenter__.return_value = response

    test_tuple = {
        "user": "user:anne",
        "relation": "reader", 
        "object": "document:budget"
    }

    await openfga_client.set_policy_data([test_tuple])
    
    # Verify request format
    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args[1]
    assert "writes" in call_kwargs["json"]

@pytest.mark.asyncio
async def test_get_data_with_input(openfga_client, mock_session, mock_response):
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
                "context": {"time": "business_hours"}
            }

    result = await openfga_client.get_data_with_input(
        path="document:budget",
        input_model=TestInput()
    )

    assert result["allowed"] is True
    assert result["resolution"] == "direct"

@pytest.mark.asyncio
async def test_retry_behavior(openfga_client, mock_session, mock_response):
    responses = [
        mock_response(status=500, data={"error": "Server Error"}),
        mock_response(status=500, data={"error": "Server Error"}),
        mock_response(status=200)
    ]
    
    mock_session.post.return_value.__aenter__.side_effect = responses

    # Override retry config for faster test
    from tenacity import stop_after_attempt
    openfga_client.set_policy_data.retry.stop = stop_after_attempt(3)

    await openfga_client.set_policy_data([{
        "user": "user:anne", 
        "relation": "reader",
        "object": "document:budget"
    }])

    assert mock_session.post.call_count == 3


@pytest.mark.asyncio
async def test_network_error(openfga_client, mock_session):
   from tenacity import RetryError
   
   mock_session.post.return_value.__aenter__.side_effect = aiohttp.ClientError()
   
   # Override retry config for faster test
   from tenacity import stop_after_attempt  
   openfga_client.set_policy_data.retry.stop = stop_after_attempt(1)
   
   with pytest.raises(RetryError):
       await openfga_client.set_policy_data([{
           "user": "user:anne",
           "relation": "reader",
           "object": "document:budget"
       }])

@pytest.mark.asyncio 
async def test_log_transaction(openfga_client):
    state = openfga_client._transaction_state
    state._policy_updater_disabled = False
    state._data_updater_disabled = False

    # Initial successful transactions
    tx1 = StoreTransaction(
        id="tx1",
        transaction_type=TransactionType.policy,
        success=True,
        actions=["set_policy"]
    )
    await openfga_client.log_transaction(tx1)
    
    tx2 = StoreTransaction(
        id="tx2", 
        transaction_type=TransactionType.data,
        success=True,
        actions=["set_data"]
    )
    await openfga_client.log_transaction(tx2)

    assert await openfga_client.is_ready()
    assert await openfga_client.is_healthy()

    # Failed transaction makes system unhealthy
    tx3 = StoreTransaction(
        id="tx3",
        transaction_type=TransactionType.data,
        success=False,
        actions=["set_data"],
        error="Test failure"
    )
    await openfga_client.log_transaction(tx3)

    assert await openfga_client.is_ready()
    assert not await openfga_client.is_healthy()

@pytest.mark.asyncio
async def test_health_check_states(openfga_client):
    state = openfga_client._transaction_state
    state._policy_updater_disabled = False  
    state._data_updater_disabled = False

    # Initially neither ready nor healthy
    assert not await openfga_client.is_ready()
    assert not await openfga_client.is_healthy()

    # Add successful policy transaction
    tx1 = StoreTransaction(
        id="tx1",
        transaction_type=TransactionType.policy,
        success=True,
        actions=["set_policy"]
    )
    await openfga_client.log_transaction(tx1)

    # Still not ready/healthy without data transaction
    assert not await openfga_client.is_ready()
    assert not await openfga_client.is_healthy()

    # Add successful data transaction
    tx2 = StoreTransaction(
        id="tx2",
        transaction_type=TransactionType.data, 
        success=True,
        actions=["set_data"]
    )
    await openfga_client.log_transaction(tx2)

    # Now ready and healthy
    assert await openfga_client.is_ready()
    assert await openfga_client.is_healthy()

    # Failed transaction makes unhealthy but still ready
    tx3 = StoreTransaction(
        id="tx3",
        transaction_type=TransactionType.policy,
        success=False,
        actions=["set_policy"],
        error="Test failure"
    )
    await openfga_client.log_transaction(tx3)

    assert await openfga_client.is_ready()
    assert not await openfga_client.is_healthy()