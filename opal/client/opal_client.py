from logging import disable
import asyncio
import functools
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
from opal.client.policy.updater import PolicyUpdater, update_policy
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
            self.opa_runner = OpaRunner.setup_opa_runner(rehydration_callbacks=[
                # refetches policy code (e.g: rego) and static data from server
                functools.partial(update_policy, policy_store=self.policy_store, force_full_update=True),
                functools.partial(self.data_updater.get_base_policy_data, data_fetch_reason="policy store rehydration"),
            ])
        else:
            self.opa_runner = False

        # init fastapi app
        self.app: FastAPI = self._init_fast_api_app()

    def _init_fast_api_app(self):
        """
        inits the fastapi app object
        """
        app = FastAPI(
            title="OPAL client Sidecar",
            description="This sidecar wraps Open Policy Agent (OPA) with a higher-level API intended for fine grained " +
            "application-level authorization. The sidecar automatically handles pulling policy updates in real-time " +
            "from a centrally managed cloud-service (api.authorizon.com).",
            version="0.1.0",
            openapi_tags=OPENAPI_TAGS_METADATA
        )
        configure_middleware(app)
        self._configure_api_routes(app)
        self._configure_lifecycle_callbacks(app)
        return app

    def _configure_api_routes(self, app: FastAPI):
        """
        mounts the api routes on the app object
        """
        # Init api routers with required dependencies
        enforcer_router = init_enforcer_api_router(policy_store=self.policy_store)
        local_router = init_local_cache_api_router(policy_store=self.policy_store)
        policy_router = init_policy_router(policy_store=self.policy_store)

        # mount the api routes on the app object
        app.include_router(enforcer_router, tags=["Authorization API"])
        app.include_router(local_router, prefix="/local", tags=["Local Queries"])
        app.include_router(policy_router, tags=["Policy Updater"])
        app.include_router(data_router, tags=["Data Updater"])
        app.include_router(proxy_router, tags=["Cloud API Proxy"])

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
            asyncio.create_task(self.start_client_background_tasks(), name="opa_runner")

        @app.on_event("shutdown")
        async def shutdown_event():
            await self.stop_client_background_tasks()

        return app

    async def start_client_background_tasks(self):
        """
        Launch OPAL client long-running tasks:
        - Policy Store runner (e.g: Opa Runner)
        - Policy Updater
        - Data Updater

        If there is a policy store to run, we wait until its up before launching dependent tasks.
        """
        if self.opa_runner:
            # runs the policy store dependent tasks after policy store is up
            self.opa_runner.on_opa_initial_start([self.launch_policy_store_dependent_tasks])
            async with self.opa_runner:
                await self.opa_runner.wait_until_done()
        else:
            # we do not run the policy store in the same container
            # therefore we can immediately launch dependent tasks
            await self.launch_policy_store_dependent_tasks()

    async def stop_client_background_tasks(self):
        """
        stops all background tasks (called on shutdown event)
        """
        if self.opa_runner:
            await self.opa_runner.stop()
        if self.data_updater:
            await self.data_updater.stop()
        if self.policy_updater:
            await self.policy_updater.stop()

    async def launch_policy_store_dependent_tasks(self):
        asyncio.create_task(self.launch_policy_updater(), name="policy_updater")
        asyncio.create_task(self.launch_data_updater(), name="data_updater")

    async def launch_policy_updater(self):
        if self.policy_updater:
            async with self.policy_updater:
                await self.policy_updater.wait_until_done()

    async def launch_data_updater(self):
        if self.data_updater:
            async with self.data_updater:
                await self.data_updater.wait_until_done()