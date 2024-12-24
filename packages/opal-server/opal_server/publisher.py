from fastapi_websocket_pubsub import PubSubClient, Topic
from opal_common.confi.confi import load_conf_if_none
from opal_common.topics.publisher import (
    ClientSideTopicPublisher,
    PeriodicPublisher,
    ServerSideTopicPublisher,
    TopicPublisher,
)
from opal_common.utils import get_authorization_header
from opal_server.config import opal_server_config


def setup_publisher_task(
    server_uri: str = None,
    server_token: str = None,
) -> TopicPublisher:
    server_uri = load_conf_if_none(
        server_uri,
        opal_server_config.OPAL_WS_LOCAL_URL,
    )
    server_token = load_conf_if_none(
        server_token,
        opal_server_config.OPAL_WS_TOKEN,
    )
    return ClientSideTopicPublisher(
        client=PubSubClient(extra_headers=[get_authorization_header(server_token)]),
        server_uri=server_uri,
    )


def setup_broadcaster_keepalive_task(
    publisher: ServerSideTopicPublisher,
    time_interval: int,
    topic: Topic = "__broadcast_session_keepalive__",
) -> PeriodicPublisher:
    """a periodic publisher with the intent to trigger messages on the
    broadcast channel, so that the session to the backbone won't become idle
    and close on the backbone end."""
    return PeriodicPublisher(
        publisher, time_interval, topic, task_name="broadcaster keepalive task"
    )
