import pytest
from aiohttp import ClientSession
from opal_client.policy_store.openfga_client import OpenFGAClient
from opal_client.policy_store.schemas import PolicyStoreAuth

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

    return MockResponse

@pytest.fixture
def mock_session(mocker, mock_response):
    """Create a mocked aiohttp ClientSession"""
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
    client = OpenFGAClient(
        openfga_server_url="http://example.com",
        openfga_auth_token="test-token", 
        auth_type=PolicyStoreAuth.TOKEN
    )
    assert client._token == "test-token"
    assert client._auth_type == PolicyStoreAuth.TOKEN

def test_constructor_with_invalid_oauth():
    """Test that client fails with invalid OAuth configuration."""
    with pytest.raises(ValueError, match="OpenFGA doesn't support OAuth"):
        OpenFGAClient(
            openfga_server_url="http://example.com",
            auth_type=PolicyStoreAuth.OAUTH
        )

@pytest.mark.asyncio
async def test_set_policy(openfga_client, mock_session, mock_response):
    # Set up success response
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

@pytest.mark.asyncio
async def test_set_policy_data(openfga_client, mock_session, mock_response):
    # Set up success response 
    response = mock_response(status=200)
    mock_session.post.return_value.__aenter__.return_value = response

    await openfga_client.set_policy_data([{
        "user": "user:anne",
        "relation": "reader",
        "object": "document:budget"
    }])

    # Verify the call was made with correct data
    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args[1]
    assert "writes" in call_kwargs["json"]

@pytest.mark.asyncio
async def test_get_data_with_input(openfga_client, mock_session, mock_response):
    # Set up response with resolution
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

@pytest.mark.asyncio
async def test_retry_behavior(openfga_client, mock_session, mock_response):
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