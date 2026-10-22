"""Client info must mask sensitive websocket query param values.

``/pubsub_client_info`` reports each connected client's websocket query
params. Values of sensitive keys (``SENSITIVE_QUERY_PARAMS``, e.g. a
``?token=`` on a client's pubsub URL) must be masked; other params and the
key names are reported as before.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_server.pubsub import OPAL_CLIENT_INFO_CLIENT_ID, ClientTracker, PubSub
from starlette.datastructures import QueryParams

FAKE_TOKEN = "FAKE-KEY-123"
FAKE_API_KEY = "FAKE-KEY-456"
QUERY = (
    f"{OPAL_CLIENT_INFO_CLIENT_ID}=fake-client&token={FAKE_TOKEN}"
    f"&API_KEY={FAKE_API_KEY}&region=eu-1"
)
EXPECTED_PARAMS = {
    OPAL_CLIENT_INFO_CLIENT_ID: "fake-client",
    "token": "***",
    "API_KEY": "***",
    "region": "eu-1",
}


def test_client_tracker_masks_sensitive_query_params():
    tracker = ClientTracker()

    with tracker.new_client("10.0.0.1", 4242, QueryParams(QUERY)) as client_info:
        assert client_info.client_id == "fake-client"
        assert client_info.query_params == EXPECTED_PARAMS
        for value in (FAKE_TOKEN, FAKE_API_KEY):
            assert value not in repr(client_info)


def test_pubsub_client_info_route_masks_sensitive_query_params():
    pubsub = PubSub(signer=object(), broadcaster_uri=None)
    app = FastAPI()
    app.include_router(pubsub.api_router)
    client = TestClient(app)

    with pubsub.client_tracker.new_client("10.0.0.1", 4242, QueryParams(QUERY)):
        response = client.get("/pubsub_client_info")

    assert response.status_code == 200
    assert response.json()["fake-client"]["query_params"] == EXPECTED_PARAMS
    for value in (FAKE_TOKEN, FAKE_API_KEY):
        assert value not in response.text
