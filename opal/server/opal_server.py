import asyncio
from functools import partial
from typing import Optional

from fastapi import Depends, FastAPI

from opal.common.topics.listener import TopicListener
from opal.common.topics.publisher import TopicPublisher
from opal.common.logger import get_logger
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


logger = get_logger("opal.server")


class OpalServer:

    def __init__(self,
                 init_git_watcher=True,
                 init_publisher=True,
                 data_sources_config=None,
                 broadcaster_uri=BROADCAST_URI) -> None:

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
            if init_publisher:
                async with publisher:
                    if init_git_watcher:
                        self.leadership_lock = NamedLock(LEADER_LOCK_FILE_PATH)
                        async with self.leadership_lock:
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
            if publisher is not None:
                await publisher.stop()
            if self.webhook_listener is not None:
                await self.webhook_listener.stop()
            if self.watcher is not None:
                self.watcher.signal_stop()
