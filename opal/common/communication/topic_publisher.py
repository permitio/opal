import re
import asyncio

from typing import Optional, Any

from fastapi_websocket_pubsub import PubSubClient, TopicList
from fastapi_websocket_rpc import RpcChannel

from opal.common.logger import get_logger
from opal.common.utils import AsyncioEventLoopThread, get_authorization_header
from opal.server.config import OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN


logger = get_logger("opal.publisher-thread")


class TopicPublisherThread:
    """
    Runs a PubSubClient in a separate thread, and exposes
    publishing messages on that thread asyncio event loop.
    """
    def __init__(self, client: PubSubClient, server_uri: str):
        """[summary]

        Args:
            client (PubSubClient): a configured not-yet-started pub sub client
                we want to start in the publisher thread
            server_uri (str): the URI of the pub sub server we publish to
        """
        self._thread = AsyncioEventLoopThread(name="TopicPublisherThread")
        self._client = client
        self._server_uri = server_uri

    def start(self):
        """
        starts the publisher thread and runs the client in the thread's event loop.
        the client will attempt to connect to the pubsub server until successful.
        """
        logger.info("Launching publisher thread")
        self._thread.create_task(self._run_client())
        self._thread.start()

    async def stop(self):
        """
        stops the pubsub client, and then stops the thread.
        """
        logger.info("Stopping publisher thread")
        await self._client.disconnect()
        self._thread.stop()

    def publish(self, topics: TopicList, data: Any = None):
        """
        publish a message by launching a task on the thread's event loop.

        Args:
            topics (TopicList): a list of topics to publish the message to
            data (Any): optional data to publish as part of the message
        """
        return self._thread.create_task(self._publish(topics=topics, data=data))

    async def _run_client(self):
        """
        starts the client in the thread's event loop
        """
        self._client.start_client(f"{self._server_uri}", loop=self._thread.loop)

    async def _publish(self, topics: TopicList, data: Any = None) -> bool:
        """
        Do not trigger directly, must be triggered via publish()
        in order to run inside the publisher thread's event loop.
        """
        await self._client.wait_until_ready()
        return await self._client.publish(topics, data)