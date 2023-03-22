import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from typing import Dict, Generator, List, Optional, Set, Tuple, Union, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, WebSocket
from fastapi_websocket_pubsub import (
    ALL_TOPICS,
    EventBroadcaster,
    PubSubEndpoint,
    TopicList,
)
from fastapi_websocket_pubsub.event_notifier import (
    EventCallback,
    SubscriberId,
    Subscription,
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
from pydantic import BaseModel
from starlette.datastructures import QueryParams

OPAL_CLIENT_INFO_PARAM_PREFIX = "__opal_"
OPAL_CLIENT_INFO_CLIENT_ID = f"{OPAL_CLIENT_INFO_PARAM_PREFIX}client_id"


class ClientInfo(BaseModel):
    client_id: str
    source_host: Optional[str]
    source_port: Optional[int]
    connect_time: float
    subscribed_topics: Set[str] = set()
    refcount: int = 0  # Only change this while locking ClientTracker._client_lock
    query_params: Dict[str, str]


current_client: ContextVar[ClientInfo] = ContextVar("current_client")


class ClientTracker:
    def __init__(self):
        self._clients_by_ids: Dict[str, ClientInfo] = {}
        self._client_lock = Lock()

    def clients(self) -> Dict[str, ClientInfo]:
        return dict(self._clients_by_ids)

    @contextmanager
    def new_client(
        self,
        source_host: Optional[str],
        source_port: Optional[int],
        query_params: QueryParams,
    ) -> Generator[ClientInfo, None, None]:
        client_id = f"opal:{uuid4().hex}"
        if OPAL_CLIENT_INFO_CLIENT_ID in query_params:
            client_id = query_params.get(OPAL_CLIENT_INFO_CLIENT_ID)
        elif source_host is not None and source_port is not None:
            client_id = f"host:{source_host}:{source_port}"
        with self._client_lock:
            client_info = self._clients_by_ids.pop(client_id, None)
            if client_info is None:
                client_info = ClientInfo(
                    client_id=client_id,
                    source_host=source_host,
                    source_port=source_port,
                    connect_time=time.time(),
                    query_params=query_params,
                )
            client_info.refcount += 1
            self._clients_by_ids[client_id] = client_info
        yield client_info
        with self._client_lock:
            client_info = self._clients_by_ids.pop(client_id)
            client_info.refcount -= 1
            if client_info.refcount >= 1:
                self._clients_by_ids[client_id] = client_info

    async def on_subscribe(
        self,
        subscriber_id: SubscriberId,
        topics: Union[TopicList, ALL_TOPICS],
    ):
        if not isinstance(topics, list):
            topics = [topics]

        client_info = current_client.get(None)

        # on_subscribe is sometimes called for the broadcaster, when there is no "current client"
        if client_info is not None:
            client_info.subscribed_topics.update(topics)

    async def on_unsubscribe(
        self,
        subscriber_id: SubscriberId,
        topics: Union[TopicList, ALL_TOPICS],
    ):
        if not isinstance(topics, list):
            topics = [topics]

        client_info = current_client.get(None)

        # on_subscribe is sometimes called for the broadcaster, when there is no "current client"
        if client_info is not None:
            client_info.subscribed_topics.difference_update(topics)


class PubSub:
    """Wrapper for the Pub/Sub channel used for both policy and data
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
        self.pubsub_router = APIRouter()
        self.api_router = APIRouter()
        # Pub/Sub Internals
        self.notifier = WebSocketRpcEventNotifier()
        self.notifier.add_channel_restriction(type(self)._verify_permitted_topics)
        self.client_tracker = ClientTracker()
        self.notifier.register_subscribe_event(self.client_tracker.on_subscribe)
        self.notifier.register_unsubscribe_event(self.client_tracker.on_unsubscribe)

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

        @self.api_router.get(
            "/pubsub_client_info", response_model=Dict[str, ClientInfo]
        )
        async def client_info():
            return self.client_tracker.clients()

        @self.pubsub_router.websocket("/ws")
        async def websocket_rpc_endpoint(
            websocket: WebSocket, claims: Optional[JWTClaims] = Depends(authenticator)
        ):
            """this is the main websocket endpoint the sidecar uses to register
            on policy updates.

            as you can see, this endpoint is protected by an HTTP
            Authorization Bearer token.
            """
            try:
                if claims is None:
                    logger.info(
                        "Closing connection, remote address: {remote_address}",
                        remote_address=websocket.client,
                        reason="Authentication failed",
                    )
                    return

                source_host = None
                source_port = None
                if websocket.client is not None:
                    source_host = websocket.client.host
                    source_port = websocket.client.port
                with self.client_tracker.new_client(
                    source_host, source_port, websocket.query_params
                ) as client_info:
                    token = current_client.set(client_info)
                    try:
                        await self.endpoint.main_loop(websocket, claims=claims)
                    finally:
                        current_client.reset(token)
            finally:
                await websocket.close()

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
