import os
import asyncio
from functools import partial
from typing import Optional

from fastapi import Depends, FastAPI

from opal.common.topics.listener import TopicListener
from opal.common.topics.publisher import TopicPublisher
from opal.common.logger import logger
from opal.common.synchronization.named_lock import NamedLock
from opal.common.middleware import configure_middleware
from opal.server.config import DATA_CONFIG_SOURCES, BROADCAST_URI, LEADER_LOCK_FILE_PATH
from opal.server.data.api import init_data_updates_router
from opal.server.data.data_update_publisher import DataUpdatePublisher
from opal.server.deps.authentication import verify_logged_in
from opal.server.policy.bundles.api import router as bundles_router
from opal.server.policy.github_webhook.api import init_git_webhook_router
from opal.server.policy.github_webhook.listener import setup_webhook_listener
from opal.server.policy.watcher import (setup_watcher_task,
                                        trigger_repo_watcher_pull)
from opal.server.policy.watcher.task import RepoWatcherTask
from opal.server.publisher import setup_publisher_task
from opal.server.pubsub import PubSub


class OpalServer:

    def __init__(self,
                 init_git_watcher=True,
                 init_publisher=True,
                 data_sources_config=None,
                 broadcaster_uri=BROADCAST_URI) -> None:
        """
        Args:
            init_git_watcher (bool, optional): whether or not to launch the policy repo watcher.
            init_publisher (bool, optional): whether or not to launch a publisher pub/sub client.
                this publisher is used by the server processes to publish data to the client.
            data_sources_config (DataSourceConfig, optional): base data configuration. the opal
            broadcaster_uri (str, optional): Which server/medium should the PubSub use for broadcasting.
                Defaults to BROADCAST_URI.

            The server can run in multiple workers (by gunicorn or uvicorn).

            Every worker of the server launches the following internal components:
                publisher (PubSubClient): a client that is used to publish updates to the client.
                data_update_publisher (DataUpdatePublisher): a specialized publisher for data updates.

            Besides the components above, the works are also deciding among themselves
            on a *leader* worker (the first worker to obtain a file-lock) that also
            launches the following internal components:

                webhook_listener (TopicListener): *each* worker can receive messages from
                github on its webhook api route. regardless of the worker receiving the
                webhook request, the worker will broadcast via the pub/sub to the webhook
                topic. only the *leader* worker runs the webhook_listener and listens on
                the webhook topic. upon receiving a message on this topic, the leader will
                trigger the repo watcher to check for updates.

                watcher (RepoWatcherTask): run by the leader, monitors the policy git repository
                by polling on it or by being triggered from the webhook_listener. upon being
                triggered, will detect updates to the policy (new commits) and will update
                the opal client via pubsub.
        """

        publisher: Optional[TopicPublisher] = None
        data_update_publisher: Optional[DataUpdatePublisher] = None
        self.webhook_listener: Optional[TopicListener] = None
        self.watcher: Optional[RepoWatcherTask] = None
        self.leadership_lock: Optional[NamedLock] = None

        if data_sources_config is None:
            data_sources_config = DATA_CONFIG_SOURCES

        self.app = app = FastAPI(
            title="Opal Server",
            version="0.1.0",
        )
        configure_middleware(app)

        if init_publisher:
            publisher = setup_publisher_task()
            data_update_publisher = DataUpdatePublisher(publisher)

        # Init routers
        data_updates_router = init_data_updates_router(data_update_publisher, data_sources_config)
        pubsub = PubSub(broadcaster_uri=broadcaster_uri)
        webhook_router = init_git_webhook_router(pubsub.endpoint)

        # include the api routes
        app.include_router(bundles_router, tags=["Bundle Server"], dependencies=[Depends(verify_logged_in)])
        app.include_router(data_updates_router, tags=["Data Updates"], dependencies=[Depends(verify_logged_in)])
        app.include_router(webhook_router, tags=["Github Webhook"])
        app.include_router(pubsub.router, tags=["Pub/Sub"])

        @app.get("/healthcheck", include_in_schema=False)
        @app.get("/", include_in_schema=False)
        def healthcheck():
            return {"status": "ok"}

        async def start_background_tasks():
            """
            starts the background processes (as asyncio tasks) if such are configured.

            all workers will start these tasks:
            - publisher: a client that is used to publish updates to the client.

            only the leader worker (first to obtain leadership lock) will start these tasks:
            - webhook_listener: a client that listens on the webhook topic.
            - (repo) watcher: monitors the policy git repository for changes.
            """
            if init_publisher:
                async with publisher:
                    if init_git_watcher:
                        self.leadership_lock = NamedLock(LEADER_LOCK_FILE_PATH)
                        async with self.leadership_lock:
                            logger.info("leadership lock acquired, leader pid: {pid}", pid=os.getpid())
                            self.watcher = setup_watcher_task(publisher)
                            self.webhook_listener = setup_webhook_listener(partial(trigger_repo_watcher_pull, self.watcher))
                            async with self.webhook_listener:
                                async with self.watcher:
                                    await self.watcher.wait_until_should_stop()

        @app.on_event("startup")
        async def startup_event():
            logger.info("triggered startup event")
            asyncio.create_task(start_background_tasks())

        @app.on_event("shutdown")
        async def shutdown_event():
            logger.info("triggered shutdown event")
            if self.watcher is not None:
                self.watcher.signal_stop()
            if self.webhook_listener is not None:
                asyncio.create_task(self.webhook_listener.stop())
            if publisher is not None:
                asyncio.create_task(publisher.stop())
