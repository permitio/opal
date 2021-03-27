"""
the webhook listener listens on the `webhook` topic.
the reason we need it, is because the uvicorn worker that serves
the webhook HTTP request from github is not necessarily the leader
worker that runs the repo watcher.

The solution is quite simply: the worker that serves the request simply
publishes on the `webhook` topic, and the listener's callback is triggered.
"""

from fastapi_websocket_pubsub.pub_sub_client import PubSubClient, Topic
from opal_common.utils import get_authorization_header
from opal_common.topics.listener import TopicListener, TopicCallback
from opal_server.config import OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN


def setup_webhook_listener(
    callback: TopicCallback,
    server_uri: str = OPAL_WS_LOCAL_URL,
    server_token: str = OPAL_WS_TOKEN,
    topic: Topic = "webhook",
) -> TopicListener:
    return TopicListener(
        client=PubSubClient(
            extra_headers=[get_authorization_header(server_token)]
        ),
        server_uri=server_uri,
        topics=[topic],
        callback=callback,
    )