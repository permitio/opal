import json
from opal_server.security.api import init_security_router
from opal_server.security.jwks import JwksStaticEndpoint
import os
import asyncio
from functools import partial
from typing import Optional
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from opal_common.topics.publisher import TopicPublisher, ServerSideTopicPublisher
from opal_common.logger import logger
from opal_common.schemas.data import DataSourceConfig
from opal_common.synchronization.named_lock import NamedLock
from opal_common.middleware import configure_middleware
from opal_common.authentication.signer import JWTSigner
from opal_server.config import (
    REPO_WATCHER_ENABLED,
    PUBLISHER_ENABLED,
    DATA_CONFIG_SOURCES,
    BROADCAST_URI,
    LEADER_LOCK_FILE_PATH,
    AUTH_PRIVATE_KEY,
    AUTH_PUBLIC_KEY,
    AUTH_MASTER_TOKEN,
    AUTH_JWT_ALGORITHM,
    AUTH_JWT_AUDIENCE,
    AUTH_JWT_ISSUER,
    AUTH_JWKS_URL,
    AUTH_JWKS_STATIC_DIR,
    POLICY_REPO_URL,
    POLICY_REPO_WEBHOOK_TOPIC
)
from opal_server.data.api import init_data_updates_router
from opal_server.data.data_update_publisher import DataUpdatePublisher
from opal_server.deps.authentication import JWTVerifier, StaticBearerTokenVerifier
from opal_server.policy.bundles.api import router as bundles_router
from opal_server.policy.github_webhook.api import init_git_webhook_router
from opal_server.policy.watcher import (setup_watcher_task,
                                        trigger_repo_watcher_pull)
from opal_server.policy.watcher.task import RepoWatcherTask
from opal_server.publisher import setup_publisher_task
from opal_server.pubsub import PubSub


class OpalServer:

    def __init__(
        self,
        init_git_watcher: bool = REPO_WATCHER_ENABLED,
        policy_repo_url: str = POLICY_REPO_URL,
        init_publisher: bool = PUBLISHER_ENABLED,
        data_sources_config: Optional[DataSourceConfig] = None,
        broadcaster_uri: str = BROADCAST_URI,
        signer: Optional[JWTSigner] = None,
        jwks_url: str = AUTH_JWKS_URL,
        jwks_static_dir: str = AUTH_JWKS_STATIC_DIR,
        master_token: str = AUTH_MASTER_TOKEN,
    ) -> None:
        """
        Args:
            init_git_watcher (bool, optional): whether or not to launch the policy repo watcher.
            policy_repo_url (str, optional): the url of the repo watched by policy repo watcher.
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

                watcher (RepoWatcherTask): run by the leader, monitors the policy git repository
                by polling on it or by being triggered by the callback subscribed on the "webhook"
                topic. upon being triggered, will detect updates to the policy (new commits) and
                will update the opal client via pubsub.
        """
        self.watcher: Optional[RepoWatcherTask] = None
        self.leadership_lock: Optional[NamedLock] = None
        self.data_sources_config = data_sources_config if data_sources_config is not None else DATA_CONFIG_SOURCES
        self.broadcaster_uri = broadcaster_uri
        self.master_token = master_token

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

        self.jwks_endpoint = JwksStaticEndpoint(
            signer=self.signer,
            jwks_url=jwks_url,
            jwks_static_dir=jwks_static_dir
        )

        self.pubsub = PubSub(signer=self.signer, broadcaster_uri=broadcaster_uri)

        self.publisher: Optional[TopicPublisher] = None
        if init_publisher:
            self.publisher = ServerSideTopicPublisher(self.pubsub.endpoint)

            if init_git_watcher:
                if policy_repo_url is not None:
                    self.watcher = setup_watcher_task(self.publisher)
                else:
                    logger.warning("POLICY_REPO_URL is unset but repo watcher is enabled! disabling watcher.")

        # init fastapi app
        self.app: FastAPI = self._init_fast_api_app()

    def _init_fast_api_app(self):
        """
        inits the fastapi app object
        """
        app = FastAPI(
            title="Opal Server",
            description="OPAL is an administration layer for Open Policy Agent (OPA), detecting changes" + \
            " to both policy and data and pushing live updates to your agents. The opal server creates" + \
            " a pub/sub channel clients can subscribe to (i.e: acts as coordinator). The server also" + \
            " tracks a git repository (via webhook) for updates to policy (or static data) and accepts" + \
            " continuous data update notifications via REST api, which are then pushed to clients.",
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
        webhook_router = init_git_webhook_router(self.pubsub.endpoint)
        security_router = init_security_router(self.signer, StaticBearerTokenVerifier(self.master_token))

        verifier = JWTVerifier(self.signer)

        # mount the api routes on the app object
        app.include_router(bundles_router, tags=["Bundle Server"], dependencies=[Depends(verifier)])
        app.include_router(data_updates_router, tags=["Data Updates"], dependencies=[Depends(verifier)])
        app.include_router(webhook_router, tags=["Github Webhook"])
        app.include_router(security_router, tags=["Security"])
        app.include_router(self.pubsub.router, tags=["Pub/Sub"])

        # mount jwts (static) route
        self.jwks_endpoint.configure_app(app)

        # top level routes (i.e: healthchecks)
        @app.get("/healthcheck", include_in_schema=False)
        @app.get("/", include_in_schema=False)
        def healthcheck():
            return {"status": "ok"}

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
            if self.publisher is not None:
                asyncio.create_task(self.publisher.stop())

        return app

    async def start_server_background_tasks(self):
        """
        starts the background processes (as asyncio tasks) if such are configured.

        all workers will start these tasks:
        - publisher: a client that is used to publish updates to the client.

        only the leader worker (first to obtain leadership lock) will start these tasks:
        - (repo) watcher: monitors the policy git repository for changes.
        """
        if self.publisher is not None:
            async with self.publisher:
                if self.watcher is not None:
                    # repo watcher is enabled, but we want only one worker to run it
                    # (otherwise for each new commit, we will publish multiple updates via pub/sub).
                    # leadership is determined by the first worker to obtain a lock
                    self.leadership_lock = NamedLock(LEADER_LOCK_FILE_PATH)
                    async with self.leadership_lock:
                        # only one worker gets here, the others block. in case the leader worker
                        # is terminated, another one will obtain the lock and become leader.
                        logger.info("leadership lock acquired, leader pid: {pid}", pid=os.getpid())
                        logger.info("listening on webhook topic: '{topic}'", topic=POLICY_REPO_WEBHOOK_TOPIC)
                        # the leader listens to the webhook topic (webhook api route can be hit randomly in all workers)
                        # and triggers the watcher to check for changes in the tracked upstream remote.
                        await self.pubsub.endpoint.subscribe([POLICY_REPO_WEBHOOK_TOPIC], partial(trigger_repo_watcher_pull, self.watcher))
                        # running the watcher, and waiting until it stops (until self.watcher.signal_stop() is called)
                        async with self.watcher:
                            await self.watcher.wait_until_should_stop()