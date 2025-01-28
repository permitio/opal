import asyncio
import os
import signal
from typing import Any, Coroutine, List, Optional

from fastapi_websocket_pubsub import Topic
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.logger import logger
from opal_common.monitoring.tracing_utils import start_span
from opal_common.sources.base_policy_source import BasePolicySource
from opal_server.config import opal_server_config


class BasePolicyWatcherTask:
    """Manages the asyncio tasks of the policy watcher."""

    def __init__(self, pubsub_endpoint: PubSubEndpoint):
        self._tasks: List[asyncio.Task] = []
        self._should_stop: Optional[asyncio.Event] = None
        self._pubsub_endpoint = pubsub_endpoint
        self._webhook_tasks: List[asyncio.Task] = []

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def _on_webhook(self, topic: Topic, data: Any):
        logger.info(f"Webhook listener triggered ({len(self._webhook_tasks)})")
        for task in self._webhook_tasks:
            if task.done():
                # Clean references to finished tasks
                self._webhook_tasks.remove(task)

        self._webhook_tasks.append(asyncio.create_task(self.trigger(topic, data)))

    async def _listen_to_webhook_notifications(self):
        # Webhook api route can be hit randomly in all workers, so it publishes a message to the webhook topic.
        # This listener, running in the leader's context, would actually trigger the repo pull

        async def _subscribe_internal():
            logger.info(
                "listening on webhook topic: '{topic}'",
                topic=opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
            )
            await self._pubsub_endpoint.subscribe(
                [opal_server_config.POLICY_REPO_WEBHOOK_TOPIC],
                self._on_webhook,
            )

        if self._pubsub_endpoint.broadcaster is not None:
            async with self._pubsub_endpoint.broadcaster.get_listening_context():
                await _subscribe_internal()
                await self._pubsub_endpoint.broadcaster.get_reader_task()

                # Stop the watcher if broadcaster disconnects
                self.signal_stop()
        else:
            # If no broadcaster is configured, just subscribe, no need to wait on anything
            await _subscribe_internal()

    async def start(self):
        """Starts the policy watcher and registers a failure callback to
        terminate gracefully."""
        logger.info("Launching policy watcher")
        self._tasks.append(asyncio.create_task(self._listen_to_webhook_notifications()))
        self._init_should_stop()

    async def stop(self):
        """Stops all policy watcher tasks."""
        logger.info("Stopping policy watcher")
        for task in self._tasks + self._webhook_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def trigger(self, topic: Topic, data: Any):
        """Triggers the policy watcher from outside to check for changes (git
        pull)"""
        raise NotImplementedError()

    def wait_until_should_stop(self) -> Coroutine:
        """Waits until self.signal_stop() is called on the watcher.

        allows us to keep the repo watcher context alive until signalled
        to stop from outside.
        """
        self._init_should_stop()
        return self._should_stop.wait()

    def signal_stop(self):
        """Signal the repo watcher it should stop."""
        self._init_should_stop()
        self._should_stop.set()

    def _init_should_stop(self):
        if self._should_stop is None:
            self._should_stop = asyncio.Event()

    async def _fail(self, exc: Exception):
        """Called when the watcher fails, and stops all tasks gracefully."""
        logger.error("policy watcher failed with exception: {err}", err=repr(exc))
        self.signal_stop()
        # trigger uvicorn graceful shutdown
        os.kill(os.getpid(), signal.SIGTERM)


class PolicyWatcherTask(BasePolicyWatcherTask):
    def __init__(self, policy_source: BasePolicySource, *args, **kwargs):
        self._watcher = policy_source
        super().__init__(*args, **kwargs)

    async def start(self):
        await super().start()
        self._watcher.add_on_failure_callback(self._fail)
        self._tasks.append(asyncio.create_task(self._watcher.run()))

    async def stop(self):
        await self._watcher.stop()
        return await super().stop()

    async def trigger(self, topic: Topic, data: Any):
        """Triggers the policy watcher from outside to check for changes (git
        pull)"""
        try:
            async with start_span("opal_server_policy_update") as span:
                if span is not None:
                    span.set_attribute("topic", str(topic))
                await self._watcher.check_for_changes()
        except Exception as e:
            raise
