import asyncio
from typing import Any, Optional, Set

from ddtrace import tracer
from fastapi_websocket_pubsub import PubSubEndpoint, Topic, TopicList
from opal_common.async_utils import TasksPool
from opal_common.logger import logger


class TopicPublisher:
    """abstract publisher, base class for client side and server side
    publisher."""

    def __init__(self):
        """inits the publisher's asyncio tasks list."""
        self._pool = TasksPool()

    async def publish(self, topics: TopicList, data: Any = None):
        raise NotImplementedError()

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """starts the publisher."""
        logger.debug("started topic publisher")

    async def stop(self):
        """stops the publisher (cancels any running publishing tasks)"""
        logger.debug("stopping topic publisher")
        await self._pool.join()


class ServerSideTopicPublisher(TopicPublisher):
    """A simple wrapper around a PubSubEndpoint that exposes publish()."""

    def __init__(self, endpoint: PubSubEndpoint):
        """inits the publisher.

        Args:
            endpoint (PubSubEndpoint): a pub/sub endpoint
        """
        self._endpoint = endpoint
        super().__init__()

    async def publish(self, topics: TopicList, data: Any = None):
        await self._add_task(asyncio.create_task(self._publish_impl(topics, data)))
