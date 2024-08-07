import asyncio
from typing import Any, Optional

from opal_common.logger import logger

from fastapi_websocket_pubsub import Topic, TopicList


class Publisher:
    """abstract publisher, base class for client side and server side
    publisher."""

    async def publish(self, topics: TopicList, data: Any = None):
        raise NotImplementedError()

    async def publish_sync(self, topics: TopicList, data: Any = None):
        raise NotImplementedError()


class PeriodicPublisher:
    """Wrapper for a task that publishes to topic on fixed interval
    periodically."""

    def __init__(
        self,
        publisher: Publisher,
        time_interval: int,
        topic: Topic,
        message: Any = None,
        task_name: str = "periodic publish task",
    ):
        """inits the publisher.

        Args:
            publisher (Publisher): can publish messages on the pub/sub channel
            time_interval (int): the time interval between publishing consecutive messages
            topic (Topic): the topic to publish on
            message (Any): the message to publish
        """
        self._publisher = publisher
        self._interval = time_interval
        self._topic = topic
        self._message = message
        self._task_name = task_name
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """starts the periodic publisher task."""
        if self._task is not None:
            logger.warning(f"{self._task_name} already started")
            return

        logger.info(
            f"started {self._task_name}: topic is '{self._topic}', interval is {self._interval} seconds"
        )
        self._task = asyncio.create_task(self._publish_task())

    async def stop(self):
        """stops the publisher (cancels any running publishing tasks)"""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info(f"cancelled {self._task_name} to topic: {self._topic}")

    async def _publish_task(self):
        while True:
            await asyncio.sleep(self._interval)
            logger.info(
                f"{self._task_name}: publishing message on topic '{self._topic}', next publish is scheduled in {self._interval} seconds"
            )
            try:
                await self._publisher.publish_sync([self._topic], self._message)
            except asyncio.CancelledError:
                logger.debug(
                    f"{self._task_name} for topic '{self._topic}' was cancelled"
                )
                break
            except Exception as e:
                logger.error(
                    f"failed to publish periodic message on topic '{self._topic}': {e}"
                )
