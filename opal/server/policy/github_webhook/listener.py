from opal.common.utils import get_authorization_header
from opal.common.communication.topic_listener import TopicListenerThread
from opal.server.policy.watcher import trigger_webhook
from opal.server.config import (
    OPAL_WS_LOCAL_URL,
    OPAL_WS_TOKEN
)

# the webhook listener listens on the "webhook" topic.
# the reason we need it, is because the uvicorn worker
# that got the webhook request from github is not necessarily
# the leader worker that runs the repo watcher.
# therefore the api worker that gets the request simply
# publishes the "webhook" topic, and the listener's callback is triggered.
webhook_listener = TopicListenerThread(
    server_uri=OPAL_WS_LOCAL_URL,
    topics=["webhook"],
    callback=trigger_webhook,
    extra_headers=[get_authorization_header(OPAL_WS_TOKEN)]
)