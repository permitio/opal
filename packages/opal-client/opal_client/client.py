import asyncio
import functools
import os
import signal
import uuid
from logging import disable
from typing import List, Optional

import aiohttp
import websockets
from fastapi import FastAPI
from opal_client.callbacks.api import init_callbacks_api
from opal_client.callbacks.register import CallbacksRegister
from opal_client.config import PolicyStoreTypes, opal_client_config
from opal_client.data.api import init_data_router
from opal_client.data.fetcher import DataFetcher
from opal_client.data.updater import DataUpdater
from opal_client.limiter import StartupLoadLimiter
from opal_client.opa.options import OpaServerOptions
from opal_client.opa.runner import OpaRunner
from opal_client.policy.api import init_policy_router
from opal_client.policy.updater import PolicyUpdater
from opal_client.policy_store.api import init_policy_store_router
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.policy_store.policy_store_client_factory import (
    PolicyStoreClientFactory,
)
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.verifier import JWTVerifier
from opal_common.config import opal_common_config
from opal_common.logger import configure_logs, logger
from opal_common.middleware import configure_middleware
from opal_common.security.sslcontext import get_custom_ssl_context


class OpalClient:
    def __init__(
        self,
        policy_store_type: PolicyStoreTypes = None,
        policy_store: BasePolicyStoreClient = None,
        data_updater: DataUpdater = None,
        data_topics: List[str] = None,
        policy_updater: PolicyUpdater = None,
        inline_opa_enabled: bool = None,
        inline_opa_options: OpaServerOptions = None,
        verifier: Optional[JWTVerifier] = None,
    ) -> None:
        """
        Args:
            policy_store_type (PolicyStoreTypes, optional): [description]. Defaults to POLICY_STORE_TYPE.

            Internal components (for each pass None for default init, or False to disable):
                policy_store (BasePolicyStoreClient, optional): The policy store client. Defaults to None.
                data_updater (DataUpdater, optional): Defaults to None.
                policy_updater (PolicyUpdater, optional): Defaults to None.
        """
        # defaults
        policy_store_type: PolicyStoreTypes = (
            policy_store_type or opal_client_config.POLICY_STORE_TYPE
        )
        inline_opa_enabled: bool = (
            inline_opa_enabled or opal_client_config.INLINE_OPA_ENABLED
        )
        inline_opa_options: OpaServerOptions = (
            inline_opa_options or opal_client_config.INLINE_OPA_CONFIG
        )
        opal_client_identifier: str = (
            opal_client_config.OPAL_CLIENT_STAT_ID or f"CLIENT_{uuid.uuid4().hex}"
        )
        # set logs
        configure_logs()
        # Init policy store client
        self.policy_store_type: PolicyStoreTypes = policy_store_type
        self.policy_store: BasePolicyStoreClient = (
            policy_store or PolicyStoreClientFactory.create(policy_store_type)
        )
        # data fetcher
        self.data_fetcher = DataFetcher()
        # callbacks register
        if hasattr(opal_client_config.DEFAULT_UPDATE_CALLBACKS, "callbacks"):
            default_callbacks = opal_client_config.DEFAULT_UPDATE_CALLBACKS.callbacks
        else:
            default_callbacks = []

        self._callbacks_register = CallbacksRegister(default_callbacks)

        self._startup_wait = None
        if opal_client_config.WAIT_ON_SERVER_LOAD:
            self._startup_wait = StartupLoadLimiter()

        # Init policy updater
        if policy_updater is not None:
            self.policy_updater = policy_updater
        else:
            self.policy_updater = PolicyUpdater(
                policy_store=self.policy_store,
                data_fetcher=self.data_fetcher,
                callbacks_register=self._callbacks_register,
                opal_client_id=opal_client_identifier,
            )
        # Data updating service
        if opal_client_config.DATA_UPDATER_ENABLED:
            if data_updater is not None:
                self.data_updater = data_updater
            else:
                data_topics = (
                    data_topics
                    if data_topics is not None
                    else opal_client_config.DATA_TOPICS
                )

                self.data_updater = DataUpdater(
                    policy_store=self.policy_store,
                    data_topics=data_topics,
                    data_fetcher=self.data_fetcher,
                    callbacks_register=self._callbacks_register,
                    opal_client_id=opal_client_identifier,
                )
        else:
            self.data_updater = None

        # Internal services
        # Policy store
        if self.policy_store_type == PolicyStoreTypes.OPA and inline_opa_enabled:
            rehydration_callbacks = [
                # refetches policy code (e.g: rego) and static data from server
                functools.partial(
                    self.policy_updater.update_policy, force_full_update=True
                ),
            ]

            if self.data_updater:
                rehydration_callbacks.append(
                    functools.partial(
                        self.data_updater.get_base_policy_data,
                        data_fetch_reason="policy store rehydration",
                    )
                )

            self.opa_runner = OpaRunner.setup_opa_runner(
                options=inline_opa_options,
                piped_logs_format=opal_client_config.INLINE_OPA_LOG_FORMAT,
                rehydration_callbacks=rehydration_callbacks,
            )
        else:
            self.opa_runner = False

        custom_ssl_context = get_custom_ssl_context()
        if (
            opal_common_config.CLIENT_SELF_SIGNED_CERTIFICATES_ALLOWED
            and custom_ssl_context is not None
        ):
            logger.warning(
                "OPAL client is configured to trust self-signed certificates"
            )

        if verifier is not None:
            self.verifier = verifier
        else:
            self.verifier = JWTVerifier(
                public_key=opal_common_config.AUTH_PUBLIC_KEY,
                algorithm=opal_common_config.AUTH_JWT_ALGORITHM,
                audience=opal_common_config.AUTH_JWT_AUDIENCE,
                issuer=opal_common_config.AUTH_JWT_ISSUER,
            )
        if not self.verifier.enabled:
            logger.info(
                "API authentication disabled (public encryption key was not provided)"
            )

        # init fastapi app
        self.app: FastAPI = self._init_fast_api_app()

    def _init_fast_api_app(self):
        """inits the fastapi app object."""
        app = FastAPI(
            title="OPAL Client",
            description="OPAL is an administration layer for Open Policy Agent (OPA), detecting changes"
            + " to both policy and data and pushing live updates to your agents. The opal client is"
            + " deployed alongside a policy-store (e.g: OPA), keeping it up-to-date, by connecting to"
            + " an opal-server and subscribing to pub/sub updates for policy and policy data changes.",
            version="0.1.0",
        )
        configure_middleware(app)
        self._configure_api_routes(app)
        self._configure_lifecycle_callbacks(app)
        return app

    def _configure_api_routes(self, app: FastAPI):
        """mounts the api routes on the app object."""

        authenticator = JWTAuthenticator(self.verifier)

        # Init api routers with required dependencies
        policy_router = init_policy_router(policy_updater=self.policy_updater)
        data_router = init_data_router(data_updater=self.data_updater)
        policy_store_router = init_policy_store_router(authenticator)
        callbacks_router = init_callbacks_api(authenticator, self._callbacks_register)

        # mount the api routes on the app object
        app.include_router(policy_router, tags=["Policy Updater"])
        app.include_router(data_router, tags=["Data Updater"])
        app.include_router(policy_store_router, tags=["Policy Store"])
        app.include_router(callbacks_router, tags=["Callbacks"])

        # top level routes (i.e: healthchecks)
        @app.get("/healthcheck", include_in_schema=False)
        @app.get("/", include_in_schema=False)
        def healthcheck():
            return {"status": "ok"}

        return app

    def _configure_lifecycle_callbacks(self, app: FastAPI):
        """registers callbacks on app startup and shutdown.

        on app startup we launch our long running processes (async
        tasks) on the event loop. on app shutdown we stop these long
        running tasks.
        """

        @app.on_event("startup")
        async def startup_event():
            asyncio.create_task(self.start_client_background_tasks())

        @app.on_event("shutdown")
        async def shutdown_event():
            await self.stop_client_background_tasks()

        return app

    async def start_client_background_tasks(self):
        """Launch OPAL client long-running tasks:

        - Policy Store runner (e.g: Opa Runner)
        - Policy Updater
        - Data Updater

        If there is a policy store to run, we wait until its up before launching dependent tasks.
        """
        if self._startup_wait:
            await self._startup_wait()

        if self.opa_runner:
            # runs the policy store dependent tasks after policy store is up
            self.opa_runner.register_opa_initial_start_callbacks(
                [self.launch_policy_store_dependent_tasks]
            )
            async with self.opa_runner:
                await self.opa_runner.wait_until_done()
        else:
            # we do not run the policy store in the same container
            # therefore we can immediately launch dependent tasks
            await self.launch_policy_store_dependent_tasks()

    async def stop_client_background_tasks(self):
        """stops all background tasks (called on shutdown event)"""
        logger.info("stopping background tasks...")

        # stopping opa runner
        if self.opa_runner:
            await self.opa_runner.stop()

        # stopping updater tasks (each updater runs a pub/sub client)
        logger.info("trying to shutdown DataUpdater and PolicyUpdater gracefully...")
        tasks: List[asyncio.Task] = []
        if self.data_updater:
            tasks.append(asyncio.create_task(self.data_updater.stop()))
        if self.policy_updater:
            tasks.append(asyncio.create_task(self.policy_updater.stop()))

        try:
            await asyncio.gather(*tasks)
        except Exception:
            logger.exception("exception while shutting down updaters")

    async def launch_policy_store_dependent_tasks(self):
        try:
            await self.maybe_init_healthcheck_policy()
        except Exception:
            logger.critical("healthcheck policy enabled but could not be initialized!")
            self._trigger_shutdown()
            return

        try:
            for task in asyncio.as_completed(
                [self.launch_policy_updater(), self.launch_data_updater()]
            ):
                await task
        except websockets.exceptions.InvalidStatusCode as err:
            logger.error("Failed to launch background task -- {err}", err=repr(err))
            self._trigger_shutdown()

    async def maybe_init_healthcheck_policy(self):
        """This function only runs if OPA_HEALTH_CHECK_POLICY_ENABLED is true.

        Puts the healthcheck policy in opa cache and inits the
        transaction log used by the policy. If any action fails, opal
        client will shutdown.
        """
        if not opal_client_config.OPA_HEALTH_CHECK_POLICY_ENABLED:
            return  # skip

        healthcheck_policy_relpath = opal_client_config.OPA_HEALTH_CHECK_POLICY_PATH

        here = os.path.abspath(os.path.dirname(__file__))
        healthcheck_policy_path = os.path.join(here, healthcheck_policy_relpath)
        if not os.path.exists(healthcheck_policy_path):
            logger.error(
                "Critical: OPA health-check policy is enabled, but cannot find policy at {path}",
                path=healthcheck_policy_path,
            )
            raise ValueError("OPA health check policy not found!")

        try:
            healthcheck_policy_code = open(healthcheck_policy_path, "r").read()
        except IOError as err:
            logger.error(
                "Critical: Cannot read healthcheck policy: {err}", err=repr(err)
            )
            raise

        try:
            await self.policy_store.init_healthcheck_policy(
                policy_id=healthcheck_policy_relpath,
                policy_code=healthcheck_policy_code,
                data_updater_enabled=opal_client_config.DATA_UPDATER_ENABLED,
            )
        except aiohttp.ClientError as err:
            logger.error(
                "Failed to connect to OPA agent while init healthcheck policy -- {err}",
                err=repr(err),
            )
            raise

    def _trigger_shutdown(self):
        """this will send SIGTERM (Keyboard interrupt) to the worker, making
        uvicorn send "lifespan.shutdown" event to Starlette via the ASGI
        lifespan interface.

        Starlette will then trigger the @app.on_event("shutdown")
        callback, which in our case
        (self.stop_client_background_tasks()) will gracefully shutdown
        the background processes and only then will terminate the
        worker.
        """
        logger.info("triggering shutdown with SIGTERM...")
        os.kill(os.getpid(), signal.SIGTERM)

    async def launch_policy_updater(self):
        if self.policy_updater:
            async with self.policy_updater:
                await self.policy_updater.wait_until_done()

    async def launch_data_updater(self):
        if self.data_updater:
            async with self.data_updater:
                await self.data_updater.wait_until_done()
