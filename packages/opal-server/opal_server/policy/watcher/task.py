import asyncio
import os
import signal
from typing import Any, Coroutine, List, Optional

from fastapi_websocket_pubsub import Topic
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.http_utils import redact_url_in_text
from opal_common.logger import logger
from opal_common.sources.base_policy_source import BasePolicySource
from opal_server.config import opal_server_config
from opal_server.policy.watcher.manifest import PolicyBundleSourceRegistry


class BasePolicyWatcherTask:
    """Manages the asyncio tasks of the policy watcher."""

    def __init__(self, pubsub_endpoint: PubSubEndpoint):
        self._tasks: List[asyncio.Task] = []
        self._should_stop: Optional[asyncio.Event] = None
        self._pubsub_endpoint = pubsub_endpoint
        self._webhook_tasks: List[asyncio.Task] = []
        self._webhook_topics = [opal_server_config.POLICY_REPO_WEBHOOK_TOPIC]

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def _on_webhook(self, topic: Topic, data: Any):
        logger.info(f"Webhook listener triggered ({len(self._webhook_tasks)})")
        # Rebuild rather than remove-while-iterating: list.remove() inside a
        # `for t in self._webhook_tasks` loop skips the element after each removal,
        # so finished tasks accumulate. Retrieve exceptions before dropping the
        # references — otherwise a failed trigger() is only reported by asyncio's
        # generic "Task exception was never retrieved" at GC time.
        for t in self._webhook_tasks:
            if t.done() and not t.cancelled() and t.exception() is not None:
                # git exceptions can embed a credentialed remote URL verbatim;
                # scrub here as well as in the global log patcher, which only
                # runs once configure_logs() has installed it.
                exc_text = redact_url_in_text(repr(t.exception()))
                logger.error(f"Webhook trigger task failed: {exc_text}")
        self._webhook_tasks = [t for t in self._webhook_tasks if not t.done()]
        self._webhook_tasks.append(asyncio.create_task(self.trigger(topic, data)))

    async def _listen_to_webhook_notifications(self):
        # Webhook api route can be hit randomly in all workers, so it publishes a message to the webhook topic.
        # This listener, running in the leader's context, would actually trigger the repo pull

        async def _subscribe_internal():
            logger.info(
                "listening on webhook topics: '{topics}'",
                topics=self._webhook_topics,
            )
            await self._pubsub_endpoint.subscribe(
                self._webhook_topics, self._on_webhook
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
        await asyncio.gather(*self._tasks, *self._webhook_tasks, return_exceptions=True)

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
        await self._watcher.check_for_changes()


def policy_webhook_topic(source_id: str) -> str:
    return f"{opal_server_config.POLICY_REPO_WEBHOOK_TOPIC}:{source_id}"


class MultiPolicyWatcherTask(BasePolicyWatcherTask):
    def __init__(
        self,
        policy_sources: dict,
        *args,
        manifest_registry: Optional[PolicyBundleSourceRegistry] = None,
        source_configs: Optional[dict] = None,
        source_factory=None,
        **kwargs,
    ):
        self._policy_sources = policy_sources
        self._source_configs = source_configs or {}
        self._source_tasks = {}
        self._manifest_registry = manifest_registry
        self._source_factory = source_factory
        self._manifest_refresh_task = None
        self._reconcile_lock = asyncio.Lock()
        super().__init__(*args, **kwargs)
        if self._manifest_registry is not None:
            self._webhook_topics = [opal_server_config.POLICY_REPO_WEBHOOK_TOPIC]
        else:
            self._webhook_topics = [
                policy_webhook_topic(source_id) for source_id in policy_sources
            ]

    async def start(self):
        await super().start()
        if self._manifest_registry is not None:
            self._manifest_refresh_task = asyncio.create_task(
                self._discover_and_refresh_sources()
            )
            self._tasks.append(self._manifest_refresh_task)
            return
        for source_id, source in self._policy_sources.items():
            self._start_source(source_id, source)

    def _start_source(self, source_id: str, source: BasePolicySource):
        source.add_on_failure_callback(self._fail)
        task = asyncio.create_task(self._run_source(source_id, source))
        self._source_tasks[source_id] = task
        self._tasks.append(task)

    async def _discover_and_refresh_sources(self):
        while True:
            try:
                sources = await self._manifest_registry.get_sources(force=True)
                await self._reconcile_sources(sources.sources)
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Unable to load initial API bundle manifest; retrying "
                    "(error type: {error_type})",
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(5)
        while True:
            await asyncio.sleep(self._manifest_registry.refresh_interval)
            try:
                sources = await self._manifest_registry.get_sources(force=True)
                await self._reconcile_sources(sources.sources)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Unable to refresh API bundle sources; retaining current watchers "
                    "(error type: {error_type})",
                    error_type=type(exc).__name__,
                )

    async def _reconcile_sources(self, source_configs):
        async with self._reconcile_lock:
            await self._reconcile_source_set(source_configs)

    async def _reconcile_source_set(self, source_configs):
        next_configs = {source.source_id: source for source in source_configs}
        changed_ids = {
            source_id
            for source_id, source_config in next_configs.items()
            if source_id not in self._source_configs
            or source_config.model_dump()
            != self._source_configs[source_id].model_dump()
        }
        removed_ids = set(self._source_configs).difference(next_configs)

        replacements = {
            source_id: self._source_factory(next_configs[source_id])
            for source_id in changed_ids
        }

        for source_id in removed_ids | changed_ids:
            task = self._source_tasks.pop(source_id, None)
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            old_source = self._policy_sources.pop(source_id, None)
            if old_source is not None:
                await old_source.stop()

        for source_id, source in replacements.items():
            self._policy_sources[source_id] = source
            self._source_configs[source_id] = next_configs[source_id]
            self._start_source(source_id, source)

        for source_id in removed_ids:
            self._source_configs.pop(source_id, None)

    async def _run_source(self, source_id: str, source: BasePolicySource):
        while True:
            try:
                await source.run()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "Policy source {source_id} failed during startup; retrying",
                    source_id=source_id,
                )
                await asyncio.sleep(5)

    async def stop(self):
        if self._manifest_refresh_task is not None:
            self._manifest_refresh_task.cancel()
            await asyncio.gather(
                self._manifest_refresh_task, return_exceptions=True
            )
            self._manifest_refresh_task = None
        await asyncio.gather(
            *(source.stop() for source in self._policy_sources.values()),
            return_exceptions=True,
        )
        await super().stop()

    async def trigger(self, topic: Topic, data: Any):
        if self._manifest_registry is not None:
            source_id = data.get("source_id") if isinstance(data, dict) else None
            try:
                sources = await self._manifest_registry.get_sources(force=True)
                await self._reconcile_sources(sources.sources)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Unable to reconcile manifest before webhook dispatch "
                    "(error type: {error_type})",
                    error_type=type(exc).__name__,
                )
            source = self._policy_sources.get(source_id)
            if source is not None:
                await source.check_for_changes()
            return

        topic = str(topic)
        for source_id, source in self._policy_sources.items():
            if topic == policy_webhook_topic(source_id):
                await source.check_for_changes()
                return
