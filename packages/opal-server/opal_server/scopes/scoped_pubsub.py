from typing import Any

from opal_common.logger import logger
from opal_server.pubsub import PubSub

from fastapi_websocket_pubsub import TopicList


class ScopedPubSub:
    def __init__(self, pubsub: PubSub, scope_id: str):
        self._pubsub = pubsub
        self._scope_id = scope_id

    def scope_topics(self, topics: TopicList) -> TopicList:
        topics = [f"{self._scope_id}:{topic}" for topic in topics]
        logger.debug("Publishing to topics: {topics}", topics=topics)
        return topics

    async def publish(self, topics: TopicList, data: Any = None):
        await self._pubsub.publish(self.scope_topics(topics), data)

    async def publish_sync(self, topics: TopicList, data: Any = None):
        await self._pubsub.publish_sync(self.scope_topics(topics), data)
