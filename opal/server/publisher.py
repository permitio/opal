from typing import Optional, Any

from fastapi_websocket_pubsub.pub_sub_client import PubSubClient
from opal.common.utils import get_authorization_header
from opal.common.communication.topic_publisher import TopicPublisherThread
from opal.server.config import OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN


publisher = TopicPublisherThread(
    client=PubSubClient(
        extra_headers=[get_authorization_header(OPAL_WS_TOKEN)]
    ),
    server_uri=OPAL_WS_LOCAL_URL,
)