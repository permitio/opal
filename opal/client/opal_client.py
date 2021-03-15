from logging import disable
import asyncio
from fastapi import FastAPI

from opal import common

from opal.client.config import OPENAPI_TAGS_METADATA, PolicyStoreTypes, POLICY_STORE_TYPE
from opal.client.data.api import router as data_router
from opal.client.data.updater import DataUpdater
from opal.client.enforcer.api import init_enforcer_api_router
from opal.client.local.api import init_local_cache_api_router
from opal.client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal.client.policy_store.policy_store_client_factory import PolicyStoreClientFactory
from opal.client.opa.runner import OpaRunner
from opal.client.policy.api import init_policy_router
from opal.client.policy.updater import PolicyUpdater
from opal.client.server.api import router as proxy_router
from opal.client.server.middleware import configure_middleware


class OpalClient:
    def __init__(self,
                 policy_store_type:PolicyStoreTypes=POLICY_STORE_TYPE,
                 policy_store:BasePolicyStoreClient=None,
                 data_updater:DataUpdater=None,
                 policy_updater:PolicyUpdater=None
                 ) -> None:
        """
        Args:
            policy_store_type (PolicyStoreTypes, optional): [description]. Defaults to POLICY_STORE_TYPE.

            Internal components (for each pass None for default init, or False to disable):
                policy_store (BasePolicyStoreClient, optional): The policy store client. Defaults to None.
                data_updater (DataUpdater, optional): Defaults to None.
                policy_updater (PolicyUpdater, optional): Defaults to None.
        """
        # Init policy store client
        self.policy_store_type:PolicyStoreTypes = policy_store_type
        self.policy_store:BasePolicyStoreClient = policy_store or PolicyStoreClientFactory.create(policy_store_type)
        # Init policy updater
        self.policy_updater = policy_updater if policy_updater is not None else PolicyUpdater(policy_store=self.policy_store)
        # Data updating service
        self.data_updater = data_updater if data_updater is not None else DataUpdater(policy_store=self.policy_store)

        # Internal services
        # Policy store
        if self.policy_store_type == PolicyStoreTypes.OPA:
            self.opa_runner = OpaRunner.setup_opa_runner()
        else:
            self.opa_runner = False

        # init fastapi app
        self.app: FastAPI = self._init_fast_api_app()

    def _init_fast_api_app(self):
        policy_store = self.policy_store
        app = FastAPI(
            title="OPAL client Sidecar",
            description="This sidecar wraps Open Policy Agent (OPA) with a higher-level API intended for fine grained " +
            "application-level authorization. The sidecar automatically handles pulling policy updates in real-time " +
            "from a centrally managed cloud-service (api.authorizon.com).",
            version="0.1.0",
            openapi_tags=OPENAPI_TAGS_METADATA
        )
        configure_middleware(app)

        # Init api routes
        enforcer_router = init_enforcer_api_router(policy_store=policy_store)
        local_router = init_local_cache_api_router(policy_store=policy_store)
        policy_router = init_policy_router(policy_store=policy_store)

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
            if self.opa_runner:
                self.opa_runner.start()
                # wait for opa
                await asyncio.sleep(1)
            if self.policy_updater:
                self.policy_updater.start()
            if self.data_updater:
                await self.data_updater.start()

        @app.on_event("shutdown")
        async def shutdown_event():
            if self.data_updater:
                await self.data_updater.stop()
            if self.policy_updater:
                await self.policy_updater.stop()
            if self.opa_runner:
                self.opa_runner.stop()

        return app
