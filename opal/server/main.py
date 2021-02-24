import asyncio
from fastapi import FastAPI, Depends

from opal.common.middleware import configure_middleware
from opal.server.deps.authentication import verify_logged_in
from opal.server.policy.api import router as policy_router
from opal.server.pubsub.websocket import router as websocket_router

app = FastAPI(
    title="Opal Server",
    version="0.1.0",
)
configure_middleware(app)

# include the api routes
app.include_router(policy_router, tags=["Policy"], dependencies=[Depends(verify_logged_in)])
app.include_router(websocket_router, tags=["Pub Sub"])

@app.get("/healthcheck", include_in_schema=False)
@app.get("/", include_in_schema=False)
def healthcheck():
    return {"status": "ok"}
