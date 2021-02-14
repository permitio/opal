import asyncio
from horizon.config import OPENAPI_TAGS_METADATA
from fastapi import FastAPI

from horizon.server.api import router as proxy_router
from horizon.enforcer.api import router as enforcer_router
from horizon.policy.api import router as policy_router
from horizon.local.api import router as local_router
from horizon.server.middleware import configure_middleware
from horizon.policy.updater import policy_updater
from horizon.enforcer.runner import opa_runner

app = FastAPI(
    title="Authorizon Sidecar",
    description="This sidecar wraps Open Policy Agent (OPA) with a higher-level API intended for fine grained " + \
        "application-level authorization. The sidecar automatically handles pulling policy updates in real-time " + \
        "from a centrally managed cloud-service (api.authorizon.com).",
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS_METADATA
)
configure_middleware(app)

# include the api routes
app.include_router(enforcer_router, tags=["Authorization API"])
app.include_router(local_router, prefix="/local", tags=["Local Queries"])
app.include_router(policy_router, tags=["Policy Updater"])
app.include_router(proxy_router, tags=["Cloud API Proxy"])

@app.get("/healthcheck", include_in_schema=False)
@app.get("/", include_in_schema=False)
def healthcheck():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    opa_runner.start()
    await asyncio.sleep(1) # wait for opa
    policy_updater.start()

@app.on_event("shutdown")
async def shutdown_event():
    await policy_updater.stop()
    opa_runner.stop()
