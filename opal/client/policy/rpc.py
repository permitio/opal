from typing import Coroutine, List

from fastapi_websocket_pubsub import PubSubClient
from fastapi_websocket_pubsub.event_notifier import Topic
from fastapi_websocket_pubsub.rpc_event_methods import RpcEventClientMethods, RpcMethodsBase
from opal.client.logger import get_logger
from opal.client.utils import get_authorization_header
from opal.client.config import KEEP_ALIVE_INTERVAL


TOPIC_SEPARATOR = "::"
logger = get_logger("Updater")

class AuthenticatedPubSubClient(PubSubClient):
    """
    adds HTTP Authorization header before connecting to the server's websocket.
    """
    def __init__(self, token: str, topics: List[Topic] = [], callback=None,
                 methods_class: RpcMethodsBase = None,
                 retry_config=None,
                 keep_alive: float = KEEP_ALIVE_INTERVAL,
                 on_connect: List[Coroutine] = None,
                 on_disconnect: List[Coroutine] = None,
                 server_uri = None,
                 **kwargs):
        super().__init__(
            topics=topics,
            methods_class=methods_class,
            retry_config=retry_config,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            server_uri=server_uri,
            keep_alive=keep_alive,
            extra_headers=[get_authorization_header(token)],
            **kwargs
        )


class TenantAwareRpcEventClientMethods(RpcEventClientMethods):
    """
    use this methods class when the server uses `TenantAwareRpcEventServerMethods`.
    """
    async def notify(self, subscription=None, data=None):
        logger.info("Received notification of event", subscription=subscription, data=data)
        topic = subscription["topic"]
        if TOPIC_SEPARATOR in topic:
            topic_parts = topic.split(TOPIC_SEPARATOR)
            if len(topic_parts) > 1:
                topic = topic_parts[1] # index 0 holds the app id
        await self.client.trigger_topic(topic=topic, data=data)
