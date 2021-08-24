from opal_server.security.api import init_security_router
from opal_server.security.jwks import JwksStaticEndpoint
import os
import asyncio
from functools import partial
from typing import Optional, List
from pathlib import Path

from fastapi import Depends, FastAPI

from opal_common.topics.publisher import TopicPublisher, ServerSideTopicPublisher
from opal_common.logger import logger, configure_logs
from opal_common.schemas.data import ServerDataSourceConfig
from opal_common.synchronization.named_lock import NamedLock
from opal_common.middleware import configure_middleware
from opal_common.authentication.signer import JWTSigner
from opal_server.config import opal_server_config
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
        init_git_watcher: bool = None,
        policy_repo_url: str = None,
        init_publisher: bool = None,
        data_sources_config: Optional[ServerDataSourceConfig] = None,
        broadcaster_uri: str = None,
        signer: Optional[JWTSigner] = None,
        enable_jwks_endpoint = True,
        jwks_url: str = None,
        jwks_static_dir: str = None,
        master_token: str = None,
    ) -> None:
        """
        Args:
            init_git_watcher (bool, optional): whether or not to launch the policy repo watcher.
            policy_repo_url (str, optional): the url of the repo watched by policy repo watcher.
            init_publisher (bool, optional): whether or not to launch a publisher pub/sub client.
                this publisher is used by the server processes to publish data to the client.
            data_sources_config (ServerDataSourceConfig, optional): base data configuration. the opal
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
        # load defaults
        init_git_watcher: bool = init_git_watcher or opal_server_config.REPO_WATCHER_ENABLED
        policy_repo_url: str = policy_repo_url or opal_server_config.POLICY_REPO_URL
        init_publisher: bool = init_publisher or opal_server_config.PUBLISHER_ENABLED
        broadcaster_uri: str = broadcaster_uri or opal_server_config.BROADCAST_URI
        jwks_url: str = jwks_url or opal_server_config.AUTH_JWKS_URL
        jwks_static_dir: str = jwks_static_dir or opal_server_config.AUTH_JWKS_STATIC_DIR
        master_token: str = master_token or opal_server_config.AUTH_MASTER_TOKEN

        configure_logs()
        self.watcher: Optional[RepoWatcherTask] = None
        self.leadership_lock: Optional[NamedLock] = None

        self.data_sources_config: ServerDataSourceConfig = (
            data_sources_config if data_sources_config is not None else opal_server_config.DATA_CONFIG_SOURCES)

        self.broadcaster_uri = broadcaster_uri
        self.master_token = master_token

        if signer is not None:
            self.signer = signer
        else:
            self.signer = JWTSigner(
                private_key=opal_server_config.AUTH_PRIVATE_KEY,
                public_key=opal_server_config.AUTH_PUBLIC_KEY,
                algorithm=opal_server_config.AUTH_JWT_ALGORITHM,
                audience=opal_server_config.AUTH_JWT_AUDIENCE,
                issuer=opal_server_config.AUTH_JWT_ISSUER,
            )

        if enable_jwks_endpoint:
            self.jwks_endpoint = JwksStaticEndpoint(
                signer=self.signer,
                jwks_url=jwks_url,
                jwks_static_dir=jwks_static_dir
            )
        else:
            self.jwks_endpoint = None

        self.pubsub = PubSub(signer=self.signer, broadcaster_uri=broadcaster_uri)

        self.publisher: Optional[TopicPublisher] = None
        if init_publisher:
            self.publisher = ServerSideTopicPublisher(self.pubsub.endpoint)

            if init_git_watcher:
                self._fix_policy_repo_clone_path()
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
            description="OPAL is an administration layer for Open Policy Agent (OPA), detecting changes" +
            " to both policy and data and pushing live updates to your agents. The opal server creates" +
            " a pub/sub channel clients can subscribe to (i.e: acts as coordinator). The server also" +
            " tracks a git repository (via webhook) for updates to policy (or static data) and accepts" +
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

        if self.jwks_endpoint is not None:
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
            await self.stop_server_background_tasks()

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
                    self.leadership_lock = NamedLock(opal_server_config.LEADER_LOCK_FILE_PATH)
                    async with self.leadership_lock:
                        # only one worker gets here, the others block. in case the leader worker
                        # is terminated, another one will obtain the lock and become leader.
                        logger.info("leadership lock acquired, leader pid: {pid}", pid=os.getpid())
                        logger.info("listening on webhook topic: '{topic}'",
                                    topic=opal_server_config.POLICY_REPO_WEBHOOK_TOPIC)
                        # the leader listens to the webhook topic (webhook api route can be hit randomly in all workers)
                        # and triggers the watcher to check for changes in the tracked upstream remote.
                        await self.pubsub.endpoint.subscribe([opal_server_config.POLICY_REPO_WEBHOOK_TOPIC], partial(trigger_repo_watcher_pull, self.watcher))
                        # running the watcher, and waiting until it stops (until self.watcher.signal_stop() is called)
                        async with self.watcher:
                            await self.watcher.wait_until_should_stop()

    async def stop_server_background_tasks(self):
        logger.info("stopping background tasks...")

        tasks: List[asyncio.Task] = []

        if self.watcher is not None:
            tasks.append(asyncio.create_task(self.watcher.stop()))
        if self.publisher is not None:
            tasks.append(asyncio.create_task(self.publisher.stop()))

        try:
            await asyncio.gather(*tasks)
        except Exception:
            logger.exception("exception while shutting down background tasks")

    def _fix_policy_repo_clone_path(self):
        clone_path = Path(os.path.expanduser(opal_server_config.POLICY_REPO_CLONE_PATH))
        forbidden_paths = [Path(os.path.expanduser('~')), Path('/')]
        if clone_path in forbidden_paths:
            logger.warning("You cannot clone the policy repo directly to the homedir (~) or to the root directory (/)!")
            opal_server_config.POLICY_REPO_CLONE_PATH = os.path.join(clone_path, "regoclone")
            logger.warning(f"OPAL_POLICY_REPO_CLONE_PATH was set to: {opal_server_config.POLICY_REPO_CLONE_PATH}")