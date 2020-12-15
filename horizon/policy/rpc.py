import asyncio
import threading
import logging

from typing import Coroutine, List, Tuple

from fastapi_websocket_rpc.pubsub import EventRpcClient
from fastapi_websocket_rpc.pubsub.rpc_event_methods import RpcEventClientMethods
from fastapi_websocket_rpc.pubsub.event_notifier import Topic
from fastapi_websocket_rpc.websocket.rpc_methods import RpcMethodsBase
from horizon.logger import logger
from horizon.utils import get_authorization_header


TOPIC_SEPARATOR = "::"


class AuthenticatedEventRpcClient(EventRpcClient):
    """
    adds HTTP Authorization header before connecting to the server's websocket.
    """
    def __init__(self, token: str, topics: List[Topic] = [], methods_class=None):
        super().__init__(topics=topics, methods_class=methods_class, extra_headers=[get_authorization_header(token)])


class TenantAwareRpcEventClientMethods(RpcEventClientMethods):
    """
    use this methods class when the server uses `TenantAwareRpcEventServerMethods`.
    """
    async def notify(self, subscription=None, data=None):
        self.logger.info("Received notification of event", subscription=subscription, data=data)
        topic = subscription["topic"]
        if TOPIC_SEPARATOR in topic:
            topic_parts = topic.split(TOPIC_SEPARATOR)
            if len(topic_parts) > 1:
                topic = topic_parts[1] # index 0 holds the app id
        await self.client.act_on_topic(topic=topic, data=data)
