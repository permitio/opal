from typing import Any, Coroutine

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol

from fastapi_websocket_pubsub import PubSubClient, Topic, TopicList
from opal_common.logger import logger


class TopicCallback(Protocol):
    def __call__(self, topic: Topic, data: Any) -> Coroutine:
        ...


class TopicListener:
    """A simple wrapper around a PubSubClient that listens on a topic and runs
    a callback when messages arrive for that topic.

    Provides start() and stop() shortcuts that helps treat this client
    as a separate "process" or task that runs in the background.
    """

    def __init__(
        self,
        client: PubSubClient,
        server_uri: str,
        topics: TopicList = None,
        callback: TopicCallback = None,
    ):
        """[summary]

        Args:
            client (PubSubClient): a configured not-yet-started pub sub client
            server_uri (str): the URI of the pub sub server we subscribe to
            topics (TopicList): the topic(s) we subscribe to
            callback (TopicCallback): the (async) callback to run when a message
                arrive on one of the subsribed topics
        """
        self._client = client
        self._server_uri = server_uri
        self._topics = topics
        self._callback = callback

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """starts the pub/sub client and subscribes to the predefined topic.

        the client will attempt to connect to the pubsub server until
        successful.
        """
        logger.info("started topic listener, topics={topics}", topics=self._topics)
        for topic in self._topics:
            self._client.subscribe(topic, self._callback)
        self._client.start_client(f"{self._server_uri}")

    async def stop(self):
        """stops the pubsub client."""
        await self._client.disconnect()
        logger.info("stopped topic listener", topics=self._topics)

    async def wait_until_done(self):
        """When the listener is a used as a context manager, this method waits
        until the client is done (i.e: terminated) to prevent exiting the
        context."""
        return await self._client.wait_until_done()
