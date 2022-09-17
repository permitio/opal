import asyncio
from typing import Any, List, Optional

from fastapi_websocket_pubsub import PubSubClient, PubSubEndpoint, Topic, TopicList
from opal_common.logger import logger


class TopicPublisher:
    """abstract publisher, base class for client side and server side
    publisher."""

    def __init__(self):
        """inits the publisher's asyncio tasks list."""
        self._tasks: List[asyncio.Task] = []

    def publish(self, topics: TopicList, data: Any = None):
        raise NotImplementedError()

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """starts the publisher."""
        logger.debug("started topic publisher")

    async def wait(self):
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        """stops the publisher (cancels any running publishing tasks)"""
        logger.debug("stopping topic publisher")
        for task in self._tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


class PeriodicPublisher:
    """Wrapper for a task that publishes to topic on fixed interval
    periodically."""

    def __init__(
        self,
        publisher: TopicPublisher,
        time_interval: int,
        topic: Topic,
        message: Any = None,
        task_name: str = "periodic publish task",
    ):
        """inits the publisher.

        Args:
            publisher (TopicPublisher): can publish messages on the pub/sub channel
            interval (int): the time interval between publishing consecutive messages
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
            self._publisher.publish(topics=[self._topic], data=self._message)


class ServerSideTopicPublisher(TopicPublisher):
    """A simple wrapper around a PubSubEndpoint that exposes publish()."""

    def __init__(self, endpoint: PubSubEndpoint):
        """inits the publisher.

        Args:
            endpoint (PubSubEndpoint): a pub/sub endpoint
        """
        self._endpoint = endpoint
        super().__init__()

    def publish(self, topics: TopicList, data: Any = None):
        self._tasks.append(
            asyncio.create_task(self._endpoint.publish(topics=topics, data=data))
        )


class ClientSideTopicPublisher(TopicPublisher):
    """A simple wrapper around a PubSubClient that exposes publish().

    Provides start() and stop() shortcuts that helps treat this client
    as a separate "process" or task that runs in the background.
    """

    def __init__(self, client: PubSubClient, server_uri: str):
        """inits the publisher.

        Args:
            client (PubSubClient): a configured not-yet-started pub sub client
            server_uri (str): the URI of the pub sub server we publish to
        """
        self._client = client
        self._server_uri = server_uri
        super().__init__()

    def start(self):
        """starts the pub/sub client as a background asyncio task.

        the client will attempt to connect to the pubsub server until
        successful.
        """
        super().start()
        self._client.start_client(f"{self._server_uri}")

    async def stop(self):
        """stops the pubsub client, and cancels any publishing tasks."""
        await self._client.disconnect()
        await super().stop()

    async def wait_until_done(self):
        """When the publisher is a used as a context manager, this method waits
        until the client is done (i.e: terminated) to prevent exiting the
        context."""
        return await self._client.wait_until_done()

    def publish(self, topics: TopicList, data: Any = None):
        """publish a message by launching a background task on the event loop.

        Args:
            topics (TopicList): a list of topics to publish the message to
            data (Any): optional data to publish as part of the message
        """
        self._tasks.append(asyncio.create_task(self._publish(topics=topics, data=data)))

    async def _publish(self, topics: TopicList, data: Any = None) -> bool:
        """Do not trigger directly, must be triggered via publish() in order to
        run as a monitored background asyncio task."""
        await self._client.wait_until_ready()
        logger.info("Publishing to topics: {topics}", topics=topics)
        return await self._client.publish(topics, data)


class ScopedServerSideTopicPublisher(ServerSideTopicPublisher):
    def __init__(self, endpoint: PubSubEndpoint, scope_id: str):
        super().__init__(endpoint)
        self._scope_id = scope_id

    def publish(self, topics: TopicList, data: Any = None):
        scoped_topics = [f"{self._scope_id}:{topic}" for topic in topics]
        logger.info("Publishing to topics: {topics}", topics=scoped_topics)
        super().publish(scoped_topics, data)
