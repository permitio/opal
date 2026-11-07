import asyncio
import random
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Dict, Generator, Optional, Set, Union
from uuid import uuid4

from fastapi import APIRouter, Depends, WebSocket
from fastapi_websocket_pubsub import (
    ALL_TOPICS,
    EventBroadcaster,
    TopicList,
)
from fastapi_websocket_pubsub.event_notifier import SubscriberId
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
from opal_common.http_utils import SENSITIVE_QUERY_PARAMS
from opal_common.logger import logger
from opal_server.broadcast_uri import normalize_broadcaster_uri
from opal_server.config import opal_server_config
from opal_server.pubsub_resilience import (
    FreezablePubSubEndpoint,
    ReconnectingBroadcaster,
    SafeConnectionManager,
)
from pydantic import BaseModel
from starlette.datastructures import QueryParams

OPAL_CLIENT_INFO_PARAM_PREFIX = "__opal_"
OPAL_CLIENT_INFO_CLIENT_ID = f"{OPAL_CLIENT_INFO_PARAM_PREFIX}client_id"


class ClientInfo(BaseModel):
    client_id: str
    # NOTE: the ``= None`` defaults are load-bearing. Under pydantic v1 a bare
    # ``Optional[X]`` annotation implied a ``None`` default; under v2 it is a
    # REQUIRED field. Without them these two become required and the model (and
    # its OpenAPI contract) changes behaviour.
    source_host: Optional[str] = None
    source_port: Optional[int] = None
    connect_time: float
    subscribed_topics: Set[str] = set()
    refcount: int = 0  # Only change this while locking ClientTracker._client_lock
    query_params: Dict[str, str]


@dataclass(frozen=True)
class ClientEndpointSource:
    """Encapsulates the remote websocket address and query parameters for a connected client."""

    source_host: Optional[str]
    source_port: Optional[int]
    query_params: QueryParams


current_client: ContextVar[ClientInfo] = ContextVar("current_client")


def _mask_sensitive_query_params(query_params: QueryParams) -> Dict[str, str]:
    """Copy a client's websocket query params, masking sensitive values.

    The copy is what ``ClientInfo`` keeps and ``/pubsub_client_info``
    returns, so a ``?token=...`` on a client's pubsub URL is reported as
    ``token=***``. Keys are kept so the parameter is still visible.
    """
    return {
        key: "***" if key.lower() in SENSITIVE_QUERY_PARAMS else value
        for key, value in query_params.items()
    }


def _resolve_client_id(src: ClientEndpointSource) -> str:
    if OPAL_CLIENT_INFO_CLIENT_ID in src.query_params:
        return src.query_params.get(OPAL_CLIENT_INFO_CLIENT_ID)
    if src.source_host is not None and src.source_port is not None:
        return f"host:{src.source_host}:{src.source_port}"
    return f"opal:{uuid4().hex}"


def _normalize_topic_list(topics: Union[TopicList, ALL_TOPICS]) -> list:
    if isinstance(topics, list):
        return topics
    return [topics]


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
        source_port: Optional[int] = None,
        query_params: Optional[QueryParams] = None,
    ) -> Generator[ClientInfo, None, None]:
        src = ClientEndpointSource(
            source_host=source_host,
            source_port=source_port,
            query_params=query_params if query_params is not None else QueryParams(),
        )
        client_id = _resolve_client_id(src)
        client_info = self._acquire_client(client_id, src)
        try:
            yield client_info
        finally:
            self._release_client(client_id)

    def _acquire_client(
        self, client_id: str, src: ClientEndpointSource
    ) -> ClientInfo:
        with self._client_lock:
            client_info = self._clients_by_ids.pop(client_id, None)
            if client_info is None:
                client_info = ClientInfo(
                    client_id=client_id,
                    source_host=src.source_host,
                    source_port=src.source_port,
                    connect_time=time.time(),
                    query_params=_mask_sensitive_query_params(src.query_params),
                )
            client_info.refcount += 1
            self._clients_by_ids[client_id] = client_info
            return client_info

    def _release_client(self, client_id: str) -> None:
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
        self._mutate_current_client_topics(
            topics, lambda target, items: target.update(items)
        )

    async def on_unsubscribe(
        self,
        subscriber_id: SubscriberId,
        topics: Union[TopicList, ALL_TOPICS],
    ):
        self._mutate_current_client_topics(
            topics, lambda target, items: target.difference_update(items)
        )

    @staticmethod
    def _mutate_current_client_topics(
        topics: Union[TopicList, ALL_TOPICS],
        mutator: Callable[[Set[str], list], None],
    ) -> None:
        client_info = current_client.get(None)
        if client_info is not None:
            mutator(client_info.subscribed_topics, _normalize_topic_list(topics))


class PubSub:
    """Wrapper for the Pub/Sub channel used for both policy and data
    updates."""

    def __init__(self, signer: JWTSigner, broadcaster_uri: str = None):
        """
        Args:
            broadcaster_uri (str, optional): Which server/medium should the PubSub use for broadcasting. Defaults to BROADCAST_URI.
            None means no broadcasting.
        """
        resolved_uri = normalize_broadcaster_uri(
            load_conf_if_none(broadcaster_uri, opal_server_config.BROADCAST_URI)
        )
        self.pubsub_router = APIRouter()
        self.api_router = APIRouter()
        self.client_tracker = ClientTracker()
        self.notifier = self._create_notifier()
        self.broadcaster = self._create_broadcaster(resolved_uri)
        self.endpoint = self._create_endpoint()
        self._install_safe_connection_manager()

        if isinstance(self.broadcaster, ReconnectingBroadcaster):
            self._wire_broadcaster_resync()

        self._register_routes(WebsocketJWTAuthenticator(signer))

    def _create_notifier(self) -> WebSocketRpcEventNotifier:
        notifier = WebSocketRpcEventNotifier()
        notifier.add_channel_restriction(type(self)._verify_permitted_topics)
        notifier.add_channel_restriction(type(self)._reject_external_purge_channel)
        notifier.register_subscribe_event(self.client_tracker.on_subscribe)
        notifier.register_unsubscribe_event(self.client_tracker.on_unsubscribe)
        return notifier

    def _create_broadcaster(
        self, broadcaster_uri: Optional[str]
    ) -> Optional[EventBroadcaster]:
        if broadcaster_uri is None:
            logger.info("Pub/Sub broadcaster is off")
            return None
        if opal_server_config.BROADCAST_RECONNECT_ENABLED:
            logger.info(
                "Initializing reconnecting broadcaster for server<->server communication"
            )
            return ReconnectingBroadcaster(
                broadcaster_uri,
                notifier=self.notifier,
                channel=opal_server_config.BROADCAST_CHANNEL_NAME,
                reconnect_max_retries=opal_server_config.BROADCAST_RECONNECT_MAX_RETRIES,
                reconnect_backoff_min=opal_server_config.BROADCAST_RECONNECT_BACKOFF_MIN_SECONDS,
                reconnect_backoff_max=opal_server_config.BROADCAST_RECONNECT_BACKOFF_MAX_SECONDS,
                replay_buffer_size=opal_server_config.BROADCAST_REPLAY_BUFFER_SIZE,
                resync_settle_seconds=opal_server_config.BROADCAST_RESYNC_SETTLE_SECONDS,
            )
        logger.info("Initializing broadcaster for server<->server communication")
        return EventBroadcaster(
            broadcaster_uri,
            notifier=self.notifier,
            channel=opal_server_config.BROADCAST_CHANNEL_NAME,
        )

    def _resolve_freeze_on_disconnect(self) -> bool:
        freeze_on_disconnect = opal_server_config.BROADCAST_FREEZE_ON_DISCONNECT
        if not freeze_on_disconnect:
            return False
        if isinstance(self.broadcaster, ReconnectingBroadcaster):
            if not opal_server_config.BROADCAST_RESYNC_ON_RECONNECT:
                logger.warning(
                    "BROADCAST_FREEZE_ON_DISCONNECT is enabled but BROADCAST_RESYNC_ON_RECONNECT "
                    "is disabled — the resync is the freeze's only recovery path, so freezing is "
                    "DISABLED to avoid silently losing updates published during a backbone gap. "
                    "Re-enable BROADCAST_RESYNC_ON_RECONNECT to get the fleet-consistency freeze."
                )
                return False
            return True
        if self.broadcaster is not None:
            logger.info(
                "BROADCAST_FREEZE_ON_DISCONNECT is enabled but BROADCAST_RECONNECT_ENABLED "
                "is disabled — the freeze engages only on the reconnecting broadcaster's "
                "backbone-gap signal, so it is a no-op with the stock broadcaster."
            )
        return freeze_on_disconnect

    def _create_endpoint(self) -> FreezablePubSubEndpoint:
        return FreezablePubSubEndpoint(
            broadcaster=self.broadcaster,
            notifier=self.notifier,
            rpc_channel_get_remote_id=opal_common_config.STATISTICS_ENABLED,
            ignore_broadcaster_disconnected=not isinstance(
                self.broadcaster, ReconnectingBroadcaster
            ),
            freeze_on_disconnect=self._resolve_freeze_on_disconnect(),
            freeze_exempt_topics=[
                opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
                opal_server_config.BROADCAST_KEEPALIVE_TOPIC,
                opal_server_config.STATISTICS_WAKEUP_CHANNEL,
                opal_server_config.STATISTICS_STATE_SYNC_CHANNEL,
                opal_server_config.STATISTICS_SERVER_KEEPALIVE_CHANNEL,
                opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL,
                opal_common_config.STATISTICS_REMOVE_CLIENT_CHANNEL,
                opal_server_config.SCOPES_PURGE_CHANNEL,
            ],
        )

    def _install_safe_connection_manager(self) -> None:
        endpoint_wrapper = getattr(self.endpoint, "endpoint", None)
        if endpoint_wrapper is None or not hasattr(endpoint_wrapper, "manager"):
            raise RuntimeError(
                "Unexpected fastapi_websocket_pubsub internals: cannot install "
                "SafeConnectionManager (endpoint.endpoint.manager not found)"
            )
        endpoint_wrapper.manager = SafeConnectionManager()

    def _register_routes(self, authenticator: WebsocketJWTAuthenticator) -> None:
        @self.api_router.get(
            "/pubsub_client_info", response_model=Dict[str, ClientInfo]
        )
        async def client_info():
            return self.client_tracker.clients()

        @self.pubsub_router.websocket("/ws")
        async def websocket_rpc_endpoint(
            websocket: WebSocket, claims: Optional[JWTClaims] = Depends(authenticator)
        ):
            await self._handle_websocket_connection(websocket, claims)

    async def _handle_websocket_connection(
        self, websocket: WebSocket, claims: Optional[JWTClaims]
    ) -> None:
        try:
            if claims is None:
                logger.info(
                    "Closing connection, remote address: {remote_address}",
                    remote_address=websocket.client,
                    reason="Authentication failed",
                )
                return
            source_host = websocket.client.host if websocket.client else None
            source_port = websocket.client.port if websocket.client else None
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

    def _wire_broadcaster_resync(self):
        """Register the post-gap resync."""
        manager = self.endpoint.endpoint.manager
        broadcaster = self.broadcaster
        resync_enabled = opal_server_config.BROADCAST_RESYNC_ON_RECONNECT
        settle = opal_server_config.BROADCAST_RESYNC_SETTLE_SECONDS

        async def _on_broadcaster_reconnect():
            if not resync_enabled:
                logger.info("Broadcaster recovered after a gap; client resync disabled")
                return
            if settle > 0:
                await asyncio.sleep(random.uniform(0, settle))
            logger.warning(
                "Broadcaster recovered after a gap; resyncing this worker's clients "
                "so they re-fetch current policy + data state"
            )
            await manager.close_all_staggered()
            if settle > 0:
                await asyncio.sleep(settle)

        broadcaster.set_reconnect_callback(_on_broadcaster_reconnect)

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

    @staticmethod
    async def _reject_external_purge_channel(
        topics: Union[TopicList, ALL_TOPICS], channel: RpcChannel
    ):
        """Forbid external RPC peers from touching the scope-purge channel."""
        topic_list = [topics] if isinstance(topics, str) else list(topics)
        if (
            ALL_TOPICS in topic_list
            or opal_server_config.SCOPES_PURGE_CHANNEL in topic_list
        ):
            raise Unauthorized(
                description=(
                    f"Topic '{opal_server_config.SCOPES_PURGE_CHANNEL}' (and "
                    "ALL_TOPICS, which would receive it) is server-internal and "
                    "may not be published or subscribed by external peers"
                )
            )
