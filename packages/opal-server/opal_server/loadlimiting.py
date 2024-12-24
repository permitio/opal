from fastapi import APIRouter, Request
from opal_common.logger import logger
from slowapi import Limiter


def init_loadlimit_router(loadlimit_notation: str = None):
    """initializes a route where a client (or any other network peer) can
    inquire what opal clients are currently connected to the server and on what
    topics are they registered.

    If the OPAL server does not have statistics enabled, the route will
    return 501 Not Implemented
    """
    router = APIRouter()

    # We want to globally limit the endpoint, not per client
    limiter = Limiter(key_func=lambda: "global")

    if loadlimit_notation:
        logger.info(f"rate limiting is on, configured limit: {loadlimit_notation}")

        @router.get("/loadlimit")
        @limiter.limit(loadlimit_notation)
        async def loadlimit(request: Request):
            return

    else:

        @router.get("/loadlimit")
        async def loadlimit(request: Request):
            return

    return router
