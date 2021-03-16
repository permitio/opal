from fastapi_websocket_pubsub.rpc_event_methods import RpcEventClientMethods

from opal.client.logger import logger


class TenantAwareRpcEventClientMethods(RpcEventClientMethods):
    """
    use this methods class when the server uses `TenantAwareRpcEventServerMethods`.
    """
    TOPIC_SEPARATOR = "::"

    async def notify(self, subscription=None, data=None):
        logger.info("Received notification of event", subscription=subscription, data=data)
        topic = subscription["topic"]
        if self.TOPIC_SEPARATOR in topic:
            topic_parts = topic.split(self.TOPIC_SEPARATOR)
            if len(topic_parts) > 1:
                topic = topic_parts[1] # index 0 holds the app id
        await self.client.trigger_topic(topic=topic, data=data)
