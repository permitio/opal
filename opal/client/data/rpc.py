from fastapi_websocket_rpc.logger import logging_config, LoggingModes
logging_config.set_mode(LoggingModes.UVICORN)


from typing import Coroutine, List

from fastapi_websocket_pubsub import PubSubClient
from fastapi_websocket_pubsub.event_notifier import Topic
from fastapi_websocket_pubsub.rpc_event_methods import RpcEventClientMethods, RpcMethodsBase
from horizon.logger import get_logger
from horizon.utils import get_authorization_header
from horizon.config import KEEP_ALIVE_INTERVAL


TOPIC_SEPARATOR = "::"
logger = get_logger("Data Updater")


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
