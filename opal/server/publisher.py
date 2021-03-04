from typing import Optional, Any

from fastapi_websocket_pubsub.pub_sub_client import PubSubClient
from opal.common.utils import get_authorization_header
from opal.common.communication.topic_publisher import TopicPublisherThread
from opal.server.config import OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN


publisher = None

def setup_publisher_thread(
    server_uri: str = OPAL_WS_LOCAL_URL,
    server_token: str = OPAL_WS_TOKEN,
) -> TopicPublisherThread:
    return TopicPublisherThread(
        client=PubSubClient(
            extra_headers=[get_authorization_header(server_token)]
        ),
        server_uri=server_uri,
    )