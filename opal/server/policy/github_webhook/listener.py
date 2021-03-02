"""
the webhook listener listens on the `webhook` topic.
the reason we need it, is because the uvicorn worker that serves
the webhook HTTP request from github is not necessarily the leader
worker that runs the repo watcher.

The solution is quite simply: the worker that serves the request simply
publishes on the `webhook` topic, and the listener's callback is triggered.
"""

from fastapi_websocket_pubsub.pub_sub_client import PubSubClient
from opal.common.utils import get_authorization_header
from opal.common.communication.topic_listener import TopicListenerThread
from opal.server.policy.watcher import trigger_webhook
from opal.server.config import OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN

webhook_listener = TopicListenerThread(
    client=PubSubClient(
        extra_headers=[get_authorization_header(OPAL_WS_TOKEN)]
    ),
    server_uri=OPAL_WS_LOCAL_URL,
    topics=["webhook"],
    callback=trigger_webhook,
)