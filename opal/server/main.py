import logging
from fastapi_websocket_rpc.logger import logging_config, LoggingModes

import asyncio
from fastapi import FastAPI, Depends

from opal.common.middleware import configure_middleware
from opal.common.utils import get_authorization_header
from opal.common.logger import get_logger
from opal.common.election.pubsub_bully import PubSubBullyLeaderElection

from opal.server.deps.authentication import verify_logged_in
from opal.server.policy.github_webhook.api import router as webhook_router
from opal.server.policy.bundles.api import router as bundles_router
from opal.server.policy.watcher import repo_watcher
from opal.server.publisher import publisher
from opal.server.policy.github_webhook.listener import webhook_listener
from opal.server.pubsub import router as websocket_router
from opal.server.config import NO_RPC_LOGS, OPAL_WS_LOCAL_URL, OPAL_WS_TOKEN

if NO_RPC_LOGS:
    logging_config.set_mode(LoggingModes.UVICORN, level=logging.WARN)

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

async def on_election_desicion(descision: bool):
    elected_as_leader = descision
    if elected_as_leader:
        publisher.start()
        webhook_listener.start()
        repo_watcher.start()

@app.on_event("startup")
async def startup_event():
    election = PubSubBullyLeaderElection(
        server_uri=OPAL_WS_LOCAL_URL,
        extra_headers=[get_authorization_header(OPAL_WS_TOKEN)]
    )
    election.on_desicion(on_election_desicion)
    asyncio.create_task(election.elect())

@app.on_event("shutdown")
async def shutdown_event():
    if elected_as_leader:
        await webhook_listener.stop()
        await publisher.stop()
        repo_watcher.stop()

