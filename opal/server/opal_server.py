import asyncio
import logging
from functools import partial
from opal.server.data.data_update_publisher import DataUpdatePublisher
from typing import Optional

from fastapi import Depends, FastAPI
from fastapi_websocket_rpc.logger import LoggingModes, logging_config

from opal.common.communication.topic_listener import TopicListenerThread
from opal.common.communication.topic_publisher import TopicPublisherThread
from opal.common.election.pubsub_bully import PubSubBullyLeaderElection
from opal.common.logger import get_logger
from opal.common.middleware import configure_middleware
from opal.common.utils import get_authorization_header
from opal.server.config import DATA_CONFIG_SOURCES, NO_RPC_LOGS, OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN, BROADCAST_URI
from opal.server.data.api import init_data_updates_router
from opal.server.deps.authentication import verify_logged_in
from opal.server.policy.bundles.api import router as bundles_router
from opal.server.policy.github_webhook.api import init_git_webhook_router
from opal.server.policy.github_webhook.listener import setup_webhook_listener
from opal.server.policy.watcher import (setup_watcher_thread,
                                        trigger_repo_watcher_pull)
from opal.server.policy.watcher.watcher_thread import RepoWatcherThread
from opal.server.publisher import setup_publisher_thread
from opal.server.pubsub import PubSub

if NO_RPC_LOGS:
    logging_config.set_mode(LoggingModes.UVICORN, level=logging.WARN)

logger = get_logger("opal.server")


class OpalServer:

    def __init__(self,
                 init_git_watcher=True,
                 init_publisher=True,
                 data_sources_config=None,
                 broadcaster_uri=BROADCAST_URI) -> None:

        elected_as_leader = False
        webhook_listener: Optional[TopicListenerThread] = None
        publisher: Optional[TopicPublisherThread] = None
        data_update_publisher: Optional[DataUpdatePublisher] = None
        watcher: Optional[RepoWatcherThread] = None

        if data_sources_config is None:
            data_sources_config = DATA_CONFIG_SOURCES

        self.app = app = FastAPI(
            title="Opal Server",
            version="0.1.0",
        )
        configure_middleware(app)

        if init_publisher:
            publisher = setup_publisher_thread()
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

        async def on_election_decision(
            decision: bool,
            webhook_listener: TopicListenerThread,
            repo_watcher: RepoWatcherThread,
        ):
            elected_as_leader = decision
            if elected_as_leader:
                webhook_listener.start()
                repo_watcher.start()

        @app.on_event("startup")
        async def startup_event():
            if init_publisher:
                publisher.start()
                if init_git_watcher:
                    watcher = setup_watcher_thread(publisher)
                    webhook_listener = setup_webhook_listener(partial(trigger_repo_watcher_pull, watcher))
                    election = PubSubBullyLeaderElection(
                        server_uri=OPAL_WS_LOCAL_URL,
                        extra_headers=[get_authorization_header(OPAL_WS_TOKEN)]
                    )
                    election.on_decision(
                        partial(
                            on_election_decision,
                            webhook_listener=webhook_listener,
                            repo_watcher=watcher,
                        )
                    )
                    asyncio.create_task(election.elect())

        @app.on_event("shutdown")
        async def shutdown_event():
            if elected_as_leader:
                if webhook_listener is not None:
                    await webhook_listener.stop()
                if publisher is not None:
                    await publisher.stop()
                if watcher is not None:
                    watcher.stop()

    

