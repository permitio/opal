import json
import os
import asyncio
from functools import partial
from typing import Optional
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from opal.common.topics.listener import TopicListener
from opal.common.topics.publisher import TopicPublisher
from opal.common.logger import logger
from opal.common.schemas.data import DataSourceConfig
from opal.common.synchronization.named_lock import NamedLock
from opal.common.middleware import configure_middleware
from opal.common.authentication.signer import JWTSigner
from opal.server.config import (
    REPO_WATCHER_ENABLED,
    PUBLISHER_ENABLED,
    DATA_CONFIG_SOURCES,
    BROADCAST_URI,
    LEADER_LOCK_FILE_PATH,
    AUTH_PRIVATE_KEY,
    AUTH_PUBLIC_KEY,
    AUTH_JWT_ALGORITHM,
    AUTH_JWT_AUDIENCE,
    AUTH_JWT_ISSUER,
    AUTH_JWKS_URL,
    AUTH_JWKS_STATIC_DIR,
)
from opal.server.data.api import init_data_updates_router
from opal.server.data.data_update_publisher import DataUpdatePublisher
from opal.server.deps.authentication import JWTVerifier
from opal.server.policy.bundles.api import router as bundles_router
from opal.server.policy.github_webhook.api import init_git_webhook_router
from opal.server.policy.github_webhook.listener import setup_webhook_listener
from opal.server.policy.watcher import (setup_watcher_task,
                                        trigger_repo_watcher_pull)
from opal.server.policy.watcher.task import RepoWatcherTask
from opal.server.publisher import setup_publisher_task
from opal.server.pubsub import PubSub


class OpalServer:

    def __init__(
        self,
        init_git_watcher: bool = REPO_WATCHER_ENABLED,
        init_publisher: bool = PUBLISHER_ENABLED,
        data_sources_config: Optional[DataSourceConfig] = None,
        broadcaster_uri: str = BROADCAST_URI,
        signer: Optional[JWTSigner] = None,
        jwks_url: str = AUTH_JWKS_URL,
        jwks_static_dir: str = AUTH_JWKS_STATIC_DIR,
    ) -> None:
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

        self.webhook_listener: Optional[TopicListener] = None
        self.watcher: Optional[RepoWatcherTask] = None
        self.leadership_lock: Optional[NamedLock] = None
        self.data_sources_config = data_sources_config if data_sources_config is not None else DATA_CONFIG_SOURCES
        self.broadcaster_uri = broadcaster_uri
        self.jwks_url = Path(jwks_url)
        self.jwks_static_dir = Path(jwks_static_dir)

        self.publisher: Optional[TopicPublisher] = None
        if init_publisher:
            self.publisher = setup_publisher_task()
            if init_git_watcher:
                self.watcher = setup_watcher_task(self.publisher)

        if signer is not None:
            self.signer = signer
        else:
            self.signer = JWTSigner(
                private_key=AUTH_PRIVATE_KEY,
                public_key=AUTH_PUBLIC_KEY,
                algorithm=AUTH_JWT_ALGORITHM,
                audience=AUTH_JWT_AUDIENCE,
                issuer=AUTH_JWT_ISSUER,
            )

        # init fastapi app
        self.app: FastAPI = self._init_fast_api_app()

    def _init_fast_api_app(self):
        """
        inits the fastapi app object
        """
        app = FastAPI(
            title="Opal Server",
            description="The server creates a pub/sub channel clients can subscribe to " + \
            "(i.e: acts as coordinator). The server also tracks a git repository " + \
            "(via webhook) for updates to policy (or static data) and accepts continuous " + \
            "data update notifications via REST api, which are then pushed to clients.",
            version="0.1.0",
        )
        configure_middleware(app)
        self._configure_api_routes(app)
        self._configure_lifecycle_callbacks(app)
        return app

    def _configure_api_routes(self, app: FastAPI):
        """
        mounts the api routes on the app object
        """
        data_update_publisher: Optional[DataUpdatePublisher] = None
        if self.publisher is not None:
            data_update_publisher = DataUpdatePublisher(self.publisher)

        # Init api routers with required dependencies
        data_updates_router = init_data_updates_router(
            data_update_publisher,
            self.data_sources_config
        )
        pubsub = PubSub(signer=self.signer, broadcaster_uri=self.broadcaster_uri)
        webhook_router = init_git_webhook_router(pubsub.endpoint)
        verifier = JWTVerifier(self.signer)

        # mount the api routes on the app object
        app.include_router(bundles_router, tags=["Bundle Server"], dependencies=[Depends(verifier)])
        app.include_router(data_updates_router, tags=["Data Updates"], dependencies=[Depends(verifier)])
        app.include_router(webhook_router, tags=["Github Webhook"])
        app.include_router(pubsub.router, tags=["Pub/Sub"])

        # mount jwts (static) route
        self._configure_static_jwks_route(app)

        # top level routes (i.e: healthchecks)
        @app.get("/healthcheck", include_in_schema=False)
        @app.get("/", include_in_schema=False)
        def healthcheck():
            return {"status": "ok"}

        return app

    def _configure_static_jwks_route(self, app: FastAPI):
        # create the directory in which the jwks.json file should sit
        self.jwks_static_dir.mkdir(parents=True, exist_ok=True)

        # get the jwks contents from the signer
        jwks_contents = {}
        if self.signer.enabled:
            jwk = json.loads(self.signer.get_jwk())
            jwks_contents = {
                "keys": [jwk]
            }

        # write the jwks.json file
        filename = self.jwks_static_dir / self.jwks_url.name
        with open(filename, "w") as f:
            f.write(json.dumps(jwks_contents))

        route_url = str(self.jwks_url.parent)
        app.mount(route_url, StaticFiles(directory=str(self.jwks_static_dir)), name="jwks_dir")

        return app

    def _configure_lifecycle_callbacks(self, app: FastAPI):
        """
        registers callbacks on app startup and shutdown.

        on app startup we launch our long running processes (async tasks)
        on the event loop. on app shutdown we stop these long running tasks.
        """
        @app.on_event("startup")
        async def startup_event():
            logger.info("triggered startup event")
            asyncio.create_task(self.start_server_background_tasks())

        @app.on_event("shutdown")
        async def shutdown_event():
            logger.info("triggered shutdown event")
            if self.watcher is not None:
                self.watcher.signal_stop()
            if self.webhook_listener is not None:
                asyncio.create_task(self.webhook_listener.stop())
            if self.publisher is not None:
                asyncio.create_task(self.publisher.stop())

        return app

    async def start_server_background_tasks(self):
        """
        starts the background processes (as asyncio tasks) if such are configured.

        all workers will start these tasks:
        - publisher: a client that is used to publish updates to the client.

        only the leader worker (first to obtain leadership lock) will start these tasks:
        - webhook_listener: a client that listens on the webhook topic.
        - (repo) watcher: monitors the policy git repository for changes.
        """
        if self.publisher is not None:
            async with self.publisher:
                if self.watcher is not None:
                    self.leadership_lock = NamedLock(LEADER_LOCK_FILE_PATH)
                    async with self.leadership_lock:
                        logger.info("leadership lock acquired, leader pid: {pid}", pid=os.getpid())
                        self.webhook_listener = setup_webhook_listener(partial(trigger_repo_watcher_pull, self.watcher))
                        async with self.webhook_listener:
                            async with self.watcher:
                                await self.watcher.wait_until_should_stop()