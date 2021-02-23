import re
import asyncio

from typing import Optional, Any

from fastapi_websocket_pubsub import PubSubClient, TopicList
from fastapi_websocket_rpc import RpcChannel

from opal.common.logger import get_logger
from opal.common.utils import AsyncioEventLoopThread, get_authorization_header
from opal.server.config import OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN


logger = get_logger("Policy Publisher")


class PolicyPublisher:
    """
    Publishes changes made to policy (rego) via WS server, triggered by PolicyWatcher.
    """
    def __init__(self, server_url: str = OPAL_WS_LOCAL_URL, token: Optional[str] = OPAL_WS_TOKEN):
        self._thread = AsyncioEventLoopThread(name="PolicyPublisherThread")
        self._server_url = server_url
        self._token = token
        if self._token is None:
            self._extra_headers = None
        else:
            self._extra_headers = [get_authorization_header(self._token)]

    async def on_connect(self, client: PubSubClient, channel: RpcChannel):
        logger.info("Connected to WS Server")

    def publish_updates(self, topics: TopicList, data: Any):
        return self._thread.run_coro(self._publish(topics=topics, data=data))

    async def _publish(self, topics: TopicList, data: Any) -> bool:
        """
        Do not trigger directly, must be triggered via publish_updates()
        in order to run inside the publisher thread's event loop.
        """
        # must wait before publishing events
        await self._client.wait_until_ready()
        # publish event
        logger.info("Publishing policy update", topics=topics)
        return await self._client.publish(topics, data)

    def start(self):
        logger.info("Launching publisher")
        self._thread.create_task(self._run_client())
        self._thread.start()

    async def _run_client(self):
        self._client = PubSubClient(
            on_connect=[self.on_connect],
            extra_headers=self._extra_headers,
        )
        self._client.start_client(f"{self._server_url}", loop=self._thread.loop)

    async def stop(self):
        logger.info("Stopping publisher")
        await self._client.disconnect()
        self._thread.stop()


policy_publisher = PolicyPublisher()
