import asyncio
from fastapi import FastAPI

from opal.common.middleware import configure_middleware
from opal.server.gitwatcher.api import router as policy_router
from opal.server.gitwatcher.publisher import policy_publisher
from opal.server.gitwatcher.watcher import policy_watcher

app = FastAPI(
    title="Git Watcher",
    version="0.1.0",
)
configure_middleware(app)

# include the api routes
app.include_router(policy_router, tags=["Git Watcher"])

@app.get("/healthcheck", include_in_schema=False)
@app.get("/", include_in_schema=False)
def healthcheck():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    policy_publisher.start()
    policy_watcher.start()

@app.on_event("shutdown")
async def shutdown_event():
    policy_watcher.stop()
    policy_publisher.stop()
