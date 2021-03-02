from typing import Coroutine, Any, Protocol

from fastapi_websocket_pubsub import PubSubClient, Topic, TopicList

from opal.common.utils import AsyncioEventLoopThread
from opal.common.logger import get_logger


logger = get_logger("opal.topic-listener")


class TopicCallback(Protocol):
    def __call__(self, topic: Topic, data: Any) -> Coroutine: ...

class TopicListenerThread:
    """
    Runs a PubSubClient in a separate thread, listens to a predefined
    topic list and runs a callback when messages arrive for that topic.
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
                we want to start in the listener thread
            server_uri (str): the URI of the pub sub server we subscribe to
            topics (TopicList): the topic(s) we subscribe to
            callback (TopicCallback): the (async) callback to run when a message
                arrive on one of the subsribed topics
        """
        self._thread = AsyncioEventLoopThread(name="TopicListenerThread")
        self._client = client
        self._server_uri = server_uri
        self._topics = topics
        self._callback = callback

    def start(self):
        """
        starts the listener thread and run a pubsub client in the thread's event loop.
        the client will attempt to connect to the pubsub server until successful.
        """
        logger.info("started topic listener", topics=self._topics)
        self._thread.create_task(self._run_client())
        self._thread.start()

    async def stop(self):
        """
        stops the pubsub client, and then stops the thread.
        """
        await self._client.disconnect()
        self._thread.stop()
        logger.info("stopped topic listener", topics=self._topics)

    async def _run_client(self):
        """
        starts the client in the thread's event loop
        """
        for topic in self._topics:
            self._client.subscribe(topic, self._callback)
        self._client.start_client(f"{self._server_uri}", loop=self._thread.loop)

