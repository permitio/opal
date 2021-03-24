from typing import Optional, Any

from fastapi_websocket_pubsub.pub_sub_client import PubSubClient
from opal.common.utils import get_authorization_header
from opal.common.topics.publisher import TopicPublisher, ClientSideTopicPublisher
from opal.server.config import OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN


publisher = None

def setup_publisher_task(
    server_uri: str = OPAL_WS_LOCAL_URL,
    server_token: str = OPAL_WS_TOKEN,
) -> TopicPublisher:
    return ClientSideTopicPublisher(
        client=PubSubClient(
            extra_headers=[get_authorization_header(server_token)]
        ),
        server_uri=server_uri,
    )