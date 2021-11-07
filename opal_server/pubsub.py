from fastapi import APIRouter, Depends, WebSocket
from fastapi_websocket_pubsub import PubSubEndpoint
from opal_common.confi.confi import load_conf_if_none

from opal_common.config import opal_common_config
from opal_common.logger import logger
from opal_common.authentication.signer import JWTSigner
from opal_common.authentication.deps import WebsocketJWTAuthenticator
from opal_server.config import opal_server_config


class PubSub:
    """
    Warpper for the Pub/Sub channel used for both policy and data updates
    """

    def __init__(self, signer: JWTSigner, broadcaster_uri:str=None):
        """
        Args:
            broadcaster_uri (str, optional): Which server/medium should the PubSub use for broadcasting. Defaults to BROADCAST_URI.
            None means no broadcasting.
        """
        broadcaster_uri = load_conf_if_none(broadcaster_uri, opal_server_config.BROADCAST_URI)
        self.router = APIRouter()
        self.endpoint = PubSubEndpoint(broadcaster=broadcaster_uri, rpc_channel_get_remote_id=opal_common_config.STATISTICS_ENABLED)
        authenticator = WebsocketJWTAuthenticator(signer)

        @self.router.websocket("/ws")
        async def websocket_rpc_endpoint(websocket: WebSocket, logged_in: bool = Depends(authenticator)):
            """
            this is the main websocket endpoint the sidecar uses to register on policy updates.
            as you can see, this endpoint is protected by an HTTP Authorization Bearer token.
            """
            if not logged_in:
                logger.info("Closing connection, remote address: {remote_address}", remote_address=websocket.client, reason="Authentication failed")
                await websocket.close()
                return
            # Init PubSub main-loop with or without broadcasting
            if broadcaster_uri is not None:
                async with self.endpoint.broadcaster:
                    await self.endpoint.main_loop(websocket)
            else:
                await self.endpoint.main_loop(websocket)
