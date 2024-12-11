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
from opal_common.monitoring.otel_metrics import get_meter
from opal_server.config import opal_server_config
from pydantic import BaseModel
from starlette.datastructures import QueryParams

OPAL_CLIENT_INFO_PARAM_PREFIX = "__opal_"
OPAL_CLIENT_INFO_CLIENT_ID = f"{OPAL_CLIENT_INFO_PARAM_PREFIX}client_id"

_active_clients_counter = None
_client_data_subscriptions_counter = None


def get_active_clients_counter():
    global _active_clients_counter
    if _active_clients_counter is None:
        if not opal_common_config.ENABLE_OPENTELEMETRY_METRICS:
            return None
        meter = get_meter()
        _active_clients_counter = meter.create_counter(
            name="opal_server_active_clients",
            description="Number of active clients connected to the OPAL server",
        )
    return _active_clients_counter


def get_client_data_subscriptions_counter():
    global _client_data_subscriptions_counter
    if _client_data_subscriptions_counter is None:
        if not opal_common_config.ENABLE_OPENTELEMETRY_METRICS:
            return None
        meter = get_meter()
        _client_data_subscriptions_counter = meter.create_up_down_counter(
            name="opal_client_data_subscriptions",
            description="Number of data subscriptions per client",
        )
    return _client_data_subscriptions_counter


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
                active_clients_counter = get_active_clients_counter()
                if active_clients_counter is not None:
                    source = (
                        f"{source_host}:{source_port}"
                        if source_host and source_port
                        else "unknown"
                    )
                    active_clients_counter.add(
                        1, attributes={"client_id": client_id, "source": source}
                    )
            client_info.refcount += 1
            self._clients_by_ids[client_id] = client_info
        yield client_info
        with self._client_lock:
            client_info = self._clients_by_ids.pop(client_id)
            client_info.refcount -= 1
            if client_info.refcount >= 1:
                self._clients_by_ids[client_id] = client_info
            else:
                active_clients_counter = get_active_clients_counter()
                if active_clients_counter is not None:
                    source = (
                        f"{client_info.source_host}:{client_info.source_port}"
                        if client_info.source_host and client_info.source_port
                        else "unknown"
                    )
                    active_clients_counter.add(
                        -1, attributes={"client_id": client_id, "source": source}
                    )

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
            client_data_subscriptions_counter = get_client_data_subscriptions_counter()
            if client_data_subscriptions_counter is not None:
                for topic in topics:
                    client_data_subscriptions_counter.add(
                        1,
                        attributes={"client_id": client_info.client_id, "topic": topic},
                    )

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
            client_data_subscriptions_counter = get_client_data_subscriptions_counter()
            if client_data_subscriptions_counter is not None:
                for topic in topics:
                    client_data_subscriptions_counter.add(
                        -1,
                        attributes={"client_id": client_info.client_id, "topic": topic},
                    )


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
            """This is the main websocket endpoint the sidecar uses to register
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
