from fastapi_websocket_pubsub.rpc_event_methods import RpcEventClientMethods
from opal_client.logger import logger


class TenantAwareRpcEventClientMethods(RpcEventClientMethods):
    """use this methods class when the server uses
    `TenantAwareRpcEventServerMethods`."""

    TOPIC_SEPARATOR = "::"

    async def notify(self, subscription=None, data=None):
        topic = subscription["topic"]
        logger.info(
            "Received notification of event: {topic}",
            topic=topic,
            subscription=subscription,
            data=data,
        )
        if self.TOPIC_SEPARATOR in topic:
            topic_parts = topic.split(self.TOPIC_SEPARATOR)
            if len(topic_parts) > 1:
                topic = topic_parts[1]  # index 0 holds the app id
        await self.client.trigger_topic(topic=topic, data=data)
