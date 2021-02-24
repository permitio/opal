from fastapi import APIRouter, Depends, WebSocket

from fastapi_websocket_pubsub import PubSubEndpoint
from opal.common.logger import get_logger
from opal.server.config import BROADCAST_URI
from opal.server.deps.authentication import logged_in

logger = get_logger("Pub/Sub Server")

router = APIRouter()
endpoint = PubSubEndpoint(broadcaster=BROADCAST_URI)

@router.websocket("/ws")
async def websocket_rpc_endpoint(websocket: WebSocket, logged_in: bool = Depends(logged_in)):
    """
    this is the main websocket endpoint the sidecar uses to register on policy updates.
    as you can see, this endpoint is protected by an HTTP Authorization Bearer token.
    """
    if not logged_in:
        logger.info("Closing connection", remote_address=websocket.client, reason="Authentication failed")
        await websocket.close()
        return

    async with endpoint.broadcaster:
        await endpoint.main_loop(websocket)
