from typing import Optional, Any

from fastapi_websocket_pubsub.pub_sub_client import PubSubClient
from opal_common.confi.confi import load_conf_if_none
from opal_common.utils import get_authorization_header
from opal_common.topics.publisher import TopicPublisher, ClientSideTopicPublisher
from opal_server.config import opal_server_config


publisher = None

def setup_publisher_task(
    server_uri: str = None,
    server_token: str = None,
) -> TopicPublisher:
    server_uri = load_conf_if_none(server_uri, opal_server_config.OPAL_WS_LOCAL_URL,)
    server_token = load_conf_if_none(server_token, opal_server_config.OPAL_WS_TOKEN,)
    return ClientSideTopicPublisher(
        client=PubSubClient(
            extra_headers=[get_authorization_header(server_token)]
        ),
        server_uri=server_uri,
    )