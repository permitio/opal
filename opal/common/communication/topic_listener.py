from typing import Coroutine, Optional, Any, List, Tuple, Protocol

from fastapi_websocket_pubsub import PubSubClient, Topic, TopicList

from opal.common.logger import get_logger
from opal.common.utils import AsyncioEventLoopThread


logger = get_logger("opal.topic-listener")


class TopicCallback(Protocol):
    def __call__(self, topic: Topic, data: Any) -> Coroutine: ...

class TopicListenerThread:
    """
    Publishes changes made to policy (rego) via WS server, triggered by PolicyWatcher.
    """
    def __init__(
        self,
        server_uri: str,
        topics: TopicList = None,
        callback: TopicCallback = None,
        extra_headers: Optional[List[Tuple[str, str]]] = None,
    ):
        self._thread = AsyncioEventLoopThread(name="TopicListenerThread")
        self._server_uri = server_uri
        self._topics = topics
        self._callback = callback
        self._extra_headers = extra_headers

    def start(self):
        logger.info("started topic listener", topics=self._topics)
        self._thread.create_task(self._run_client())
        self._thread.start()

    async def _run_client(self):
        self._client = PubSubClient(
            extra_headers=self._extra_headers,
        )
        for topic in self._topics:
            self._client.subscribe(topic, self._callback)
        self._client.start_client(f"{self._server_uri}", loop=self._thread.loop)

    async def stop(self):
        await self._client.disconnect()
        self._thread.stop()
        logger.info("stopped topic listener", topics=self._topics)

