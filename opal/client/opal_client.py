import asyncio
from opal.client import policy_store
from fastapi import FastAPI

from fastapi_websocket_rpc.logger import logging_config, LoggingModes
logging_config.set_mode(LoggingModes.UVICORN)

from opal.client.config import OPENAPI_TAGS_METADATA, PolicyStoreTypes, POLICY_STORE_TYPE
from opal.client.policy_store.policy_store_client_factory import PolicyStoreClientFactory
from opal.client.server.api import router as proxy_router
from opal.client.enforcer.api import init_enforcer_api_router 
from opal.client.policy.api import init_policy_router
from opal.client.data.api import router as data_router
from opal.client.local.api import init_local_cache_api_router
from opal.client.server.middleware import configure_middleware
from opal.client.policy.updater import PolicyUpdater
from opal.client.data.updater import DataUpdater
from opal.client.enforcer.runner import OpaRunner


class OpalClient:

    def __init__(self, policy_store_type=POLICY_STORE_TYPE) -> None:
        # Init policy store client
        self.policy_store_type = policy_store_type
        self.policy_store = PolicyStoreClientFactory.create(policy_store_type)
        # Init policy updater
        self.policy_updater = PolicyUpdater()
        # Data updating service
        self.data_updater = DataUpdater(policy_store=policy_store)

        # Internal services
        # Policy store
        if self.policy_store_type == PolicyStoreTypes.OPA:
            self.opa_runner = OpaRunner.setup_opa_runner()
        else:
            self.opa_runner = None
            
        # init fastapi app
        self.app:FastAPI = self._init_fast_api_app()

    def _init_fast_api_app(self):
        policy_store = self.policy_store
        app = FastAPI(
            title="OPAL client Sidecar",
            description="This sidecar wraps Open Policy Agent (OPA) with a higher-level API intended for fine grained " + \
                "application-level authorization. The sidecar automatically handles pulling policy updates in real-time " + \
                "from a centrally managed cloud-service (api.authorizon.com).",
            version="0.1.0",
            openapi_tags=OPENAPI_TAGS_METADATA
        )
        configure_middleware(app)

        # Init api routes
        enforcer_router = init_enforcer_api_router(policy_store=policy_store)
        local_router = init_local_cache_api_router(policy_store=policy_store)
        policy_router = init_policy_router()

        # include the api routes
        app.include_router(enforcer_router, tags=["Authorization API"])
        app.include_router(local_router, prefix="/local", tags=["Local Queries"])
        app.include_router(policy_router, tags=["Policy Updater"])
        app.include_router(data_router, tags=["Data Updater"])
        app.include_router(proxy_router, tags=["Cloud API Proxy"])

        # API Routes
        @app.get("/healthcheck", include_in_schema=False)
        @app.get("/", include_in_schema=False)
        def healthcheck():
            return {"status": "ok"}

        @app.on_event("startup")
        async def startup_event():
            if self.opa_runner is not None:
                self.opa_runner.start()
                # wait for opa
                await asyncio.sleep(1) 
            self.policy_updater.start()
            await self.data_updater.start()

        @app.on_event("shutdown")
        async def shutdown_event():
            await self.data_updater.stop()
            await self.policy_updater.stop()
            if self.opa_runner is not None:
                self.opa_runner.stop()

        return app


