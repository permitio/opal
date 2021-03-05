import logging
from opal.server.policy.watcher.watcher_thread import RepoWatcherThread
from opal.common.communication.topic_publisher import TopicPublisherThread
from fastapi_websocket_rpc.logger import logging_config, LoggingModes

import asyncio
from fastapi import FastAPI, Depends
from functools import partial
from typing import Optional

from opal.common.communication.topic_listener import TopicListenerThread
from opal.common.middleware import configure_middleware
from opal.common.utils import get_authorization_header
from opal.common.logger import get_logger
from opal.common.election.pubsub_bully import PubSubBullyLeaderElection

from opal.server.deps.authentication import verify_logged_in
from opal.server.policy.github_webhook.api import router as webhook_router
from opal.server.policy.bundles.api import router as bundles_router
from opal.server.policy.watcher import setup_watcher_thread, trigger_repo_watcher_pull
from opal.server.publisher import setup_publisher_thread
from opal.server.policy.github_webhook.listener import setup_webhook_listener
from opal.server.pubsub import router as websocket_router
from opal.server.config import NO_RPC_LOGS, OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN

if NO_RPC_LOGS:
    logging_config.set_mode(LoggingModes.UVICORN, level=logging.WARN)

logger = get_logger("opal.server")

def create_app(init_git_watcher=True, init_publisher=True) -> FastAPI:
    elected_as_leader = False
    webhook_listener: Optional[TopicListenerThread] = None
    publisher: Optional[TopicPublisherThread] = None
    watcher: Optional[RepoWatcherThread] = None

    app = FastAPI(
        title="Opal Server",
        version="0.1.0",
    )
    configure_middleware(app)

    # include the api routes
    app.include_router(bundles_router, tags=["Bundle Server"], dependencies=[Depends(verify_logged_in)])
    app.include_router(webhook_router, tags=["Github Webhook"])
    app.include_router(websocket_router, tags=["Pub/Sub"])

    @app.get("/healthcheck", include_in_schema=False)
    @app.get("/", include_in_schema=False)
    def healthcheck():
        return {"status": "ok"}

    async def on_election_desicion(
        descision: bool,
        webhook_listener: TopicListenerThread,
        publisher: TopicPublisherThread,
        repo_watcher: RepoWatcherThread,
    ):
        elected_as_leader = descision
        if elected_as_leader:
            publisher.start()
            webhook_listener.start()
            repo_watcher.start()

    @app.on_event("startup")
    async def startup_event():
        if init_publisher:
            publisher = setup_publisher_thread()
            if init_git_watcher:
                watcher = setup_watcher_thread(publisher)
                webhook_listener = setup_webhook_listener(partial(trigger_repo_watcher_pull, watcher))
                election = PubSubBullyLeaderElection(
                    server_uri=OPAL_WS_LOCAL_URL,
                    extra_headers=[get_authorization_header(OPAL_WS_TOKEN)]
                )
                election.on_desicion(
                    partial(
                        on_election_desicion,
                        webhook_listener=webhook_listener,
                        publisher=publisher,
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

    return app

if __name__ == '__main__':
    create_app()