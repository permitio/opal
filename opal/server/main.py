from fastapi import FastAPI, Depends

from opal.common.middleware import configure_middleware
from opal.common.logger import get_logger
from opal.common.election.uvicorn_worker_pid import UvicornWorkerPidLeaderElection

from opal.server.deps.authentication import verify_logged_in
from opal.server.policy.github_webhook.api import router as webhook_router
from opal.server.policy.bundles.api import router as bundles_router
from opal.server.policy.watcher import policy_watcher
from opal.server.policy.publisher import policy_publisher
from opal.server.policy.github_webhook.listener import webhook_listener
from opal.server.pubsub import router as websocket_router

logger = get_logger("opal.server")

app = FastAPI(
    title="Opal Server",
    version="0.1.0",
)
configure_middleware(app)

# include the api routes
app.include_router(bundles_router, tags=["Bundle Server"], dependencies=[Depends(verify_logged_in)])
app.include_router(webhook_router, tags=["Github Webhook"])
app.include_router(websocket_router, tags=["Pub/Sub"])

@app.get("/healthcheck", include_in_schema=False)
@app.get("/", include_in_schema=False)
def healthcheck():
    return {"status": "ok"}


elected_as_leader = False

@app.on_event("startup")
async def startup_event():
    election = UvicornWorkerPidLeaderElection()
    elected_as_leader = await election.elect()
    if elected_as_leader:
        logger.info("i am the leader!")
        policy_publisher.start()
        policy_watcher.start()
        webhook_listener.start()

@app.on_event("shutdown")
async def shutdown_event():
    if elected_as_leader:
        policy_watcher.stop()
        await policy_publisher.stop()
        await webhook_listener.stop()

