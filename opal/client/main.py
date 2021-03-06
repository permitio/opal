import asyncio
from fastapi import FastAPI

from fastapi_websocket_rpc.logger import logging_config, LoggingModes
logging_config.set_mode(LoggingModes.UVICORN)

from opal.client.config import OPENAPI_TAGS_METADATA, PolicyStoreTypes, POLICY_STORE_TYPE
from opal.client.policy_store.policy_store_client_factory import PolicyStoreClientFactory
from opal.client.server.api import router as proxy_router
from opal.client.enforcer.api import init_enforcer_api_router 
from opal.client.policy.api import router as policy_router
from opal.client.data.api import router as data_router
from opal.client.local.api import init_local_cache_api_router
from opal.client.server.middleware import configure_middleware
from opal.client.policy.updater import policy_updater
from opal.client.data.updater import DataUpdater
from opal.client.enforcer.runner import OpaRunner


def main(policy_store_type=POLICY_STORE_TYPE):
    app = FastAPI(
        title="OPAL client Sidecar",
        description="This sidecar wraps Open Policy Agent (OPA) with a higher-level API intended for fine grained " + \
            "application-level authorization. The sidecar automatically handles pulling policy updates in real-time " + \
            "from a centrally managed cloud-service (api.authorizon.com).",
        version="0.1.0",
        openapi_tags=OPENAPI_TAGS_METADATA
    )
    configure_middleware(app)

    # Init policy store client
    policy_store = PolicyStoreClientFactory.create(policy_store_type)
    # Init api routes
    enforcer_router = init_enforcer_api_router(policy_store=policy_store)
    local_router = init_local_cache_api_router(policy_store=policy_store)

    # include the api routes
    app.include_router(enforcer_router, tags=["Authorization API"])
    app.include_router(local_router, prefix="/local", tags=["Local Queries"])
    app.include_router(policy_router, tags=["Policy Updater"])
    app.include_router(data_router, tags=["Data Updater"])
    app.include_router(proxy_router, tags=["Cloud API Proxy"])

    # Internal services
    # Policy store
    if policy_store_type == PolicyStoreTypes.OPA:
        opa_runner = OpaRunner.setup_opa_runner()
    else:
        opa_runner = None
    # Data updating service
    data_updater = DataUpdater(policy_store=policy_store)

    # API Routes
    @app.get("/healthcheck", include_in_schema=False)
    @app.get("/", include_in_schema=False)
    def healthcheck():
        return {"status": "ok"}

    @app.on_event("startup")
    async def startup_event():
        if opa_runner is not None:
            opa_runner.start()
            # wait for opa
            await asyncio.sleep(1) 
        policy_updater.start()
        await data_updater.start()

    @app.on_event("shutdown")
    async def shutdown_event():
        await data_updater.stop()
        await policy_updater.stop()
        if opa_runner is not None:
            opa_runner.stop()


