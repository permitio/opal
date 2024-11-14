import asyncio
import os
import signal
from typing import Any, List, Optional

from fastapi_websocket_pubsub import Topic
from opal_common.logger import logger
from opal_common.sources.base_policy_source import BasePolicySource
from opal_common.async_utils import TasksPool
from opal_server.config import opal_server_config
from opal_server.pubsub import PubSub


class BasePolicyWatcherTask:
    """Manages the asyncio tasks of the policy watcher."""

    def __init__(self, pubsub: PubSub):
        self._tasks = TasksPool()
        self._should_stop: Optional[asyncio.Event] = None
        self._pubsub = pubsub

    async def _on_webhook(self, topic: Topic, data: Any):
        logger.info("Webhook listener triggered")
        self._tasks.add_task(self.trigger(topic, data))

    async def _listen_to_webhook_notifications(self):
        # Webhook api route can be hit randomly in all workers, so it publishes a message to the webhook topic.
        # This listener, running in the leader's context, would actually trigger the repo pull
        logger.info(
            "listening on webhook topic: '{topic}'",
            topic=opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
        )
        await self._pubsub.subscribe(
            [opal_server_config.POLICY_REPO_WEBHOOK_TOPIC],
            self._on_webhook,
        )

    async def start(self):
        """starts the policy watcher and registers a failure callback to
        terminate gracefully."""
        logger.info("Launching policy watcher")
        await self._listen_to_webhook_notifications()

    async def stop(self):
        """stops all policy watcher tasks."""
        logger.info("Stopping policy watcher")
        await self._tasks.join()

    async def trigger(self, topic: Topic, data: Any):
        """triggers the policy watcher from outside to check for changes (git
        pull)"""
        raise NotImplementedError()

    async def _fail(self, exc: Exception):
        """called when the watcher fails, and stops all tasks gracefully."""
        logger.error("policy watcher failed with exception: {err}", err=repr(exc))
        # trigger uvicorn graceful shutdown
        os.kill(os.getpid(), signal.SIGTERM)


class PolicyWatcherTask(BasePolicyWatcherTask):
    def __init__(self, policy_source: BasePolicySource, *args, **kwargs):
        self._watcher = policy_source
        super().__init__(*args, **kwargs)

    async def start(self):
        await super().start()
        self._watcher.add_on_failure_callback(self._fail)
        self._tasks.add_task(self._watcher.run())

    async def stop(self):
        await self._watcher.stop()
        return await super().stop()

    async def trigger(self, topic: Topic, data: Any):
        """triggers the policy watcher from outside to check for changes (git
        pull)"""
        await self._watcher.check_for_changes()
