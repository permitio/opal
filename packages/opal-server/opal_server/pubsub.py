from typing import Optional, Union

from fastapi import APIRouter, Depends, WebSocket
from fastapi_websocket_pubsub import (
    ALL_TOPICS,
    EventBroadcaster,
    PubSubEndpoint,
    TopicList,
)
from fastapi_websocket_pubsub.websocket_rpc_event_notifier import (
    WebSocketRpcEventNotifier,
)
from fastapi_websocket_rpc import RpcChannel
from opal_common.authentication.deps import WebsocketJWTAuthenticator
from opal_common.authentication.signer import JWTSigner
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.confi.confi import load_conf_if_none
from opal_common.config import opal_common_config
from opal_common.logger import logger
from opal_server.config import opal_server_config


class PubSub:
    """Warpper for the Pub/Sub channel used for both policy and data
    updates."""

    def __init__(self, signer: JWTSigner, broadcaster_uri: str = None):
        """
        Args:
            broadcaster_uri (str, optional): Which server/medium should the PubSub use for broadcasting. Defaults to BROADCAST_URI.
            None means no broadcasting.
        """
        broadcaster_uri = load_conf_if_none(
            broadcaster_uri, opal_server_config.BROADCAST_URI
        )
        self.router = APIRouter()
        # Pub/Sub Internals
        self.notifier = WebSocketRpcEventNotifier()
        self.notifier.add_channel_restriction(type(self)._verify_permitted_topics)

        self.broadcaster = None
        if broadcaster_uri is not None:
            logger.info(f"Initializing broadcaster for server<->server communication")
            self.broadcaster = EventBroadcaster(
                broadcaster_uri,
                notifier=self.notifier,
                channel=opal_server_config.BROADCAST_CHANNEL_NAME,
            )
        else:
            logger.info("Pub/Sub broadcaster is off")

        # The server endpoint
        self.endpoint = PubSubEndpoint(
            broadcaster=self.broadcaster,
            notifier=self.notifier,
            rpc_channel_get_remote_id=opal_common_config.STATISTICS_ENABLED,
            ignore_broadcaster_disconnected=(
                not opal_server_config.BROADCAST_CONN_LOSS_BUGFIX_EXPERIMENT_ENABLED
            ),
        )
        authenticator = WebsocketJWTAuthenticator(signer)

        @self.router.websocket("/ws")
        async def websocket_rpc_endpoint(
            websocket: WebSocket, claims: Optional[JWTClaims] = Depends(authenticator)
        ):
            """this is the main websocket endpoint the sidecar uses to register
            on policy updates.

            as you can see, this endpoint is protected by an HTTP
            Authorization Bearer token.
            """
            if claims is None:
                logger.info(
                    "Closing connection, remote address: {remote_address}",
                    remote_address=websocket.client,
                    reason="Authentication failed",
                )
                await websocket.close()
                return

            await self.endpoint.main_loop(websocket, claims=claims)

    @staticmethod
    async def _verify_permitted_topics(
        topics: Union[TopicList, ALL_TOPICS], channel: RpcChannel
    ):
        if "permitted_topics" not in channel.context.get("claims", {}):
            return
        unauthorized_topics = set(topics).difference(
            channel.context["claims"]["permitted_topics"]
        )
        if unauthorized_topics:
            raise Unauthorized(
                description=f"Invalid 'topics' to subscribe {unauthorized_topics}"
            )
