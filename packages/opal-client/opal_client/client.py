import asyncio
import functools
import os
import signal
import tempfile
import uuid
from logging import disable
from typing import Awaitable, Callable, List, Literal, Optional, Union

import aiofiles
import aiofiles.os
import aiohttp
import websockets
from fastapi import FastAPI, HTTPException, Security, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_websocket_pubsub.pub_sub_client import PubSubOnConnectCallback
from fastapi_websocket_rpc.rpc_channel import OnDisconnectCallback
from opal_client.callbacks.api import init_callbacks_api
from opal_client.callbacks.register import CallbacksRegister
from opal_client.config import PolicyStoreTypes, opal_client_config
from opal_client.data.api import init_data_router
from opal_client.data.fetcher import DataFetcher
from opal_client.data.updater import DataUpdater
from opal_client.engine.options import CedarServerOptions, OpaServerOptions
from opal_client.engine.runner import CedarRunner, OpaRunner
from opal_client.limiter import StartupLoadLimiter
from opal_client.policy.api import init_policy_router
from opal_client.policy.updater import PolicyUpdater
from opal_client.policy_store.api import init_policy_store_router
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.policy_store.policy_store_client_factory import (
    PolicyStoreClientFactory,
)
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.verifier import JWTVerifier, Unauthorized
from opal_common.config import opal_common_config
from opal_common.logger import configure_logs, logger
from opal_common.middleware import configure_middleware
from opal_common.monitoring.otel_metrics import init_meter
from opal_common.monitoring.tracer import init_tracer
from opal_common.security.sslcontext import get_custom_ssl_context
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

security_scheme = HTTPBearer()


def _add_metrics_route(app: FastAPI, authenticator: JWTAuthenticator):
    """Add a protected metrics endpoint to the FastAPI app."""
    if opal_common_config.ENABLE_OPENTELEMETRY_METRICS:

        @app.get("/metrics")
        async def protected_metrics_endpoint(
            auth: HTTPAuthorizationCredentials = Security(security_scheme),
        ):
            """Protected metrics endpoint."""
            try:
                claims = authenticator(auth.credentials)
                data = generate_latest()
                return Response(content=data, media_type=CONTENT_TYPE_LATEST)
            except Unauthorized:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                )

        logger.info("Mounted protected /metrics endpoint for Prometheus metrics.")


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
        inline_cedar_enabled: bool = None,
        inline_cedar_options: CedarServerOptions = None,
        verifier: Optional[JWTVerifier] = None,
        store_backup_path: Optional[str] = None,
        store_backup_interval: Optional[int] = None,
        offline_mode_enabled: bool = False,
        shard_id: Optional[str] = None,
        on_data_updater_connect: List[PubSubOnConnectCallback] = None,
        on_data_updater_disconnect: List[OnDisconnectCallback] = None,
        on_policy_updater_connect: List[PubSubOnConnectCallback] = None,
        on_policy_updater_disconnect: List[OnDisconnectCallback] = None,
    ) -> None:
        """
        Args:
            policy_store_type (PolicyStoreTypes, optional): [description]. Defaults to POLICY_STORE_TYPE.

            Internal components (for each pass None for default init, or False to disable):
                policy_store (BasePolicyStoreClient, optional): The policy store client. Defaults to None.
                data_updater (DataUpdater, optional): Defaults to None.
                policy_updater (PolicyUpdater, optional): Defaults to None.
        """
        self._shard_id = shard_id
        # defaults
        policy_store_type: PolicyStoreTypes = (
            policy_store_type or opal_client_config.POLICY_STORE_TYPE
        )
        inline_opa_enabled: bool = (
            inline_opa_enabled or opal_client_config.INLINE_OPA_ENABLED
        )
        inline_cedar_enabled: bool = (
            inline_cedar_enabled or opal_client_config.INLINE_CEDAR_ENABLED
        )
        opal_client_identifier: str = (
            opal_client_config.OPAL_CLIENT_STAT_ID or f"CLIENT_{uuid.uuid4().hex}"
        )
        # set logs
        configure_logs()
        self._configure_monitoring()
        self.offline_mode_enabled = (
            offline_mode_enabled or opal_client_config.OFFLINE_MODE_ENABLED
        )
        if self.offline_mode_enabled and not inline_opa_enabled:
            logger.warning(
                "Offline mode was enabled, but isn't supported when using an external policy store (inline OPA is disabled)"
            )
            self.offline_mode_enabled = False

        # Init policy store client
        self.policy_store_type: PolicyStoreTypes = policy_store_type
        self.policy_store: BasePolicyStoreClient = (
            policy_store
            or PolicyStoreClientFactory.create(
                policy_store_type, offline_mode_enabled=self.offline_mode_enabled
            )
        )
        # callbacks register
        if hasattr(opal_client_config.DEFAULT_UPDATE_CALLBACKS, "callbacks"):
            default_callbacks = opal_client_config.DEFAULT_UPDATE_CALLBACKS.callbacks
        else:
            default_callbacks = []

        self._callbacks_register = CallbacksRegister(default_callbacks)

        self._startup_wait = None
        if opal_client_config.WAIT_ON_SERVER_LOAD:
            self._startup_wait = StartupLoadLimiter()

        if opal_client_config.POLICY_UPDATER_ENABLED:
            # Init policy updater
            if policy_updater is not None:
                self.policy_updater = policy_updater
            else:
                self.policy_updater = PolicyUpdater(
                    policy_store=self.policy_store,
                    callbacks_register=self._callbacks_register,
                    opal_client_id=opal_client_identifier,
                    on_connect=on_policy_updater_connect,
                    on_disconnect=on_policy_updater_disconnect,
                )
        else:
            self.policy_updater = None

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
                    callbacks_register=self._callbacks_register,
                    opal_client_id=opal_client_identifier,
                    shard_id=self._shard_id,
                    on_connect=on_data_updater_connect,
                    on_disconnect=on_data_updater_disconnect,
                )
        else:
            self.data_updater = None

        # Internal services
        # Policy store
        self.engine_runner = self._init_engine_runner(
            inline_opa_enabled,
            inline_cedar_enabled,
            inline_opa_options,
            inline_cedar_options,
        )

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
        self.store_backup_path = (
            store_backup_path or opal_client_config.STORE_BACKUP_PATH
        )
        self.store_backup_interval = (
            store_backup_interval or opal_client_config.STORE_BACKUP_INTERVAL
        )
        self._backup_loaded = False

        # init fastapi app
        self.app: FastAPI = self._init_fast_api_app()

    def _init_engine_runner(
        self,
        inline_opa_enabled: bool,
        inline_cedar_enabled: bool,
        inline_opa_options: Optional[OpaServerOptions] = None,
        inline_cedar_options: Optional[CedarServerOptions] = None,
    ) -> Union[OpaRunner, CedarRunner, Literal[False]]:
        if inline_opa_enabled and self.policy_store_type == PolicyStoreTypes.OPA:
            inline_opa_options = (
                inline_opa_options or opal_client_config.INLINE_OPA_CONFIG
            )
            rehydration_callbacks = []
            if self.policy_updater:
                rehydration_callbacks.append(
                    # refetches policy code (e.g: rego) and static data from server
                    functools.partial(
                        self.policy_updater.trigger_update_policy,
                        force_full_update=True,
                    ),
                )

            if self.data_updater:
                rehydration_callbacks.append(
                    functools.partial(
                        self.data_updater.get_base_policy_data,
                        data_fetch_reason="policy store rehydration",
                    )
                )

            return OpaRunner.setup_opa_runner(
                options=inline_opa_options,
                piped_logs_format=opal_client_config.INLINE_OPA_LOG_FORMAT,
                rehydration_callbacks=rehydration_callbacks,
            )

        elif inline_cedar_enabled and self.policy_store_type == PolicyStoreTypes.CEDAR:
            inline_cedar_options = (
                inline_cedar_options or opal_client_config.INLINE_CEDAR_CONFIG
            )
            return CedarRunner.setup_cedar_runner(
                options=inline_cedar_options,
                piped_logs_format=opal_client_config.INLINE_CEDAR_LOG_FORMAT,
            )

        return False

    def _init_fast_api_app(self):
        """Inits the fastapi app object."""
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

    def _configure_monitoring(self):
        if opal_common_config.ENABLE_OPENTELEMETRY_TRACING:
            self._initialize_opentelemetry_tracing()

        if opal_common_config.ENABLE_OPENTELEMETRY_METRICS:
            self._initialize_opentelemetry_metrics()

    def _initialize_opentelemetry_tracing(self):
        resource = Resource.create({"service.name": "opal-client"})
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        otlp_exporter = OTLPSpanExporter(
            endpoint=opal_common_config.OPENTELEMETRY_OTLP_ENDPOINT, insecure=True
        )

        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        init_tracer(tracer_provider)
        logger.info("OpenTelemetry tracing is enabled.")

    def _initialize_opentelemetry_metrics(self):
        resource = Resource.create({"service.name": "opal-client"})
        self.prometheus_metric_reader = PrometheusMetricReader()

        meter_provider = MeterProvider(
            resource=resource, metric_readers=[self.prometheus_metric_reader]
        )
        metrics.set_meter_provider(meter_provider)
        init_meter(meter_provider)
        self.meter = metrics.get_meter(__name__)

        self.startup_counter = self.meter.create_counter(
            name="startup",
            description="Number of times the application has started",
        )
        self.startup_counter.add(1)

        logger.info("OpenTelemetry metrics are enabled.")

    async def _is_ready(self):
        # Data loaded from file or from server
        return self._backup_loaded or await self.policy_store.is_ready()

    def _configure_api_routes(self, app: FastAPI):
        """Mounts the api routes on the app object."""

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
        @app.get("/healthy", include_in_schema=False)
        async def healthy():
            """Returns 200 if updates keep being successfully fetched from the
            server and applied to the policy store."""
            # TODO: Client would only report unhealthy if server -> policy-store transactions failed, but not if server connection gets disconnected.
            healthy = await self.policy_store.is_healthy()

            if healthy:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"status": "ok", "online": True},
                )
            elif self.offline_mode_enabled and await self._is_ready():
                # Offline Mode is active. That is enabled, client is "ready" (data loaded) but not "healthy" (latest updates failed).
                # TODO: Maybe if updates were fetched from server, but storing them to OPA wasn't successful, we should return 503 even with offline mode enabled
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"status": "ok", "online": False},
                )
            else:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"status": "unavailable"},
                )

        @app.get("/ready", include_in_schema=False)
        async def ready():
            """Returns 200 if the policy store is ready to serve requests."""
            if await self._is_ready():
                return JSONResponse(
                    status_code=status.HTTP_200_OK, content={"status": "ok"}
                )
            else:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"status": "unavailable"},
                )

        _add_metrics_route(app, authenticator)

        return app

    def _configure_lifecycle_callbacks(self, app: FastAPI):
        """Registers callbacks on app startup and shutdown.

        on app startup we launch our long running processes (async
        tasks) on the event loop. on app shutdown we stop these long
        running tasks.
        """

        @app.on_event("startup")
        async def startup_event():
            asyncio.create_task(self.start_client_background_tasks())

        @app.on_event("shutdown")
        async def shutdown_event():
            if self.offline_mode_enabled:
                await self.backup_store()

            await self.stop_client_background_tasks()

        return app

    async def _run_or_delay_for_engine_runner(
        self, callback: Callable[[], Awaitable[None]]
    ):
        if self.engine_runner:
            # runs the callback after policy store is up
            self.engine_runner.register_process_initial_start_callbacks([callback])
            async with self.engine_runner:
                await self.engine_runner.wait_until_done()
            return

        # we do not run the policy store in the same container
        # therefore we can immediately run the callback
        await callback()

    async def start_client_background_tasks(self):
        """Launch OPAL client long-running tasks:

        - Policy Store runner (e.g: Opa Runner)
        - Policy Updater
        - Data Updater

        If there is a policy store to run, we wait until its up before launching dependent tasks.
        """
        if self._startup_wait:
            await self._startup_wait()

        await self._run_or_delay_for_engine_runner(
            self.launch_policy_store_dependent_tasks
        )

    async def stop_client_background_tasks(self):
        """Stops all background tasks (called on shutdown event)"""
        logger.info("stopping background tasks...")

        # stopping opa runner
        if self.engine_runner:
            await self.engine_runner.stop()

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

    async def load_store_from_backup(self):
        """Imports the backup file, if exists, to the policy store."""
        try:
            if os.path.isfile(self.store_backup_path):
                async with aiofiles.open(self.store_backup_path, "r") as backup_file:
                    logger.info("importing policy store from backup file...")
                    await self.policy_store.full_import(backup_file)
                    logger.debug("import completed")
                    self._backup_loaded = True
            else:
                logger.warning("policy store backup file wasn't found")
        except Exception:
            logger.exception("failed to load backup data to policy store")

    async def backup_store(self):
        """Exports the policy store's data to a backup file."""
        try:
            async with self._backup_lock:
                await aiofiles.os.makedirs(
                    os.path.dirname(self.store_backup_path), exist_ok=True
                )
                tmp_backup_path = ""
                async with aiofiles.tempfile.NamedTemporaryFile(
                    "w",
                    delete=False,
                    dir=os.path.dirname(self.store_backup_path),
                    suffix=".json.tmp",
                ) as backup_file:
                    tmp_backup_path = backup_file.name
                    logger.debug("exporting policy store to backup file...")
                    await self.policy_store.full_export(backup_file)
                    logger.debug("export completed")

                # Atomically replace the previous backup (only after the new one is ready)
                await aiofiles.os.replace(tmp_backup_path, self.store_backup_path)
        except Exception:
            logger.exception("failed to backup policy store")

    async def periodically_backup_store(self):
        self._backup_lock = asyncio.Lock()

        # Backup store periodically
        while True:
            await asyncio.sleep(self.store_backup_interval)
            await self.backup_store()

    async def launch_policy_store_dependent_tasks(self):
        try:
            await self.maybe_init_healthcheck_policy()
        except Exception:
            logger.critical("healthcheck policy enabled but could not be initialized!")
            self._trigger_shutdown()
            return

        if self.offline_mode_enabled:
            # Immediately attempt loading from backup (waiting for failure loading from server would delay availability)
            await self.load_store_from_backup()
            asyncio.create_task(self.periodically_backup_store())

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
            with open(healthcheck_policy_path, "r") as file:
                healthcheck_policy_code = file.read()
        except IOError as err:
            logger.error(
                "Critical: Cannot read healthcheck policy: {err}", err=repr(err)
            )
            raise

        try:
            await self.policy_store.init_healthcheck_policy(
                policy_id=healthcheck_policy_relpath,
                policy_code=healthcheck_policy_code,
            )
        except aiohttp.ClientError as err:
            logger.error(
                "Failed to connect to OPA agent while init healthcheck policy -- {err}",
                err=repr(err),
            )
            raise

    def _trigger_shutdown(self):
        """This will send SIGTERM (Keyboard interrupt) to the worker, making
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
