import asyncio
import os
from datetime import datetime
from importlib.metadata import version as module_version
from random import uniform
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import opal_server
import pydantic
from fastapi import APIRouter, HTTPException, status
from fastapi_websocket_pubsub.event_notifier import Subscription, TopicList
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.async_utils import TasksPool
from opal_common.config import opal_common_config
from opal_common.logger import get_logger
from opal_common.topics.publisher import PeriodicPublisher
from opal_server.config import opal_server_config
from pydantic import BaseModel, Field


class ChannelStats(BaseModel):
    rpc_id: str
    client_id: str
    topics: TopicList


class ServerStats(BaseModel):
    uptime: datetime = Field(..., description="uptime for this opal server worker")
    version: str = Field(..., description="opal server version")
    clients: Dict[str, List[ChannelStats]] = Field(
        ...,
        description="connected opal clients, each client can have multiple subscriptions",
    )
    servers: Set[str] = Field(
        ...,
        description="list of all connected opal server replicas",
    )


class ServerStatsBrief(BaseModel):
    uptime: datetime = Field(..., description="uptime for this opal server worker")
    version: str = Field(..., description="opal server version")
    client_count: int = Field(..., description="number of connected opal clients")
    server_count: int = Field(..., description="number of opal server replicas")


class SyncRequest(BaseModel):
    requesting_worker_id: str


class SyncResponse(BaseModel):
    requesting_worker_id: str
    clients: Dict[str, List[ChannelStats]]
    rpc_id_to_client_id: Dict[str, str]


class ServerKeepalive(BaseModel):
    worker_id: str


logger = get_logger("opal.statistics")

# time to wait before sending statistics
MIN_TIME_TO_WAIT = 0.001
MAX_TIME_TO_WAIT = 5
SLEEP_TIME_FOR_BROADCASTER_READER_TO_START = 2


class OpalStatistics:
    """Manage opal server statistics.

    Args:
        endpoint:
        The pub/sub server endpoint that allows us to subscribe to the stats channel on the server side
    """

    def __init__(self, endpoint):
        self._endpoint: PubSubEndpoint = endpoint
        self._uptime = datetime.utcnow()
        self._workers_count = (lambda envar: int(envar) if envar.isdigit() else 1)(
            os.environ.get("UVICORN_NUM_WORKERS", "1")
        )

        # helps us realize when another server already responded to a sync request
        self._worker_id = uuid4().hex

        # state: Dict[str, List[ChannelStats]]
        # The state is built in this way so it will be easy to understand how much OPAL clients (vs. rpc clients)
        # you have connected to your OPAL server and to help merge client lists between servers.
        # The state is keyed by unique client id (A unique id that each opal client can set in env var `OPAL_CLIENT_STAT_ID`)
        self._state: ServerStats = ServerStats(
            uptime=self._uptime,
            clients={},
            servers={self._worker_id},
            version=module_version(opal_server.__name__),
        )

        # rpc_id_to_client_id:
        # dict to help us get client id without another loop
        self._rpc_id_to_client_id: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._synced_after_wakeup = asyncio.Event()
        self._received_sync_messages: Set[str] = set()
        self._publish_tasks = TasksPool()
        self._seen_servers: Dict[str, datetime] = {}
        self._periodic_keepalive_task: asyncio.Task | None = None

    @property
    def state(self) -> ServerStats:
        return self._state

    @property
    def state_brief(self) -> ServerStatsBrief:
        return ServerStatsBrief(
            uptime=self._state.uptime,
            version=self._state.version,
            client_count=len(self._state.clients),
            server_count=len(self._state.servers) / self._workers_count,
        )

    async def _expire_old_servers(self):
        async with self._lock:
            now = datetime.utcnow()
            still_alive = {}
            for server_id, last_seen in self._seen_servers.items():
                if (now - last_seen).total_seconds() < float(
                    opal_server_config.STATISTICS_SERVER_KEEPALIVE_TIMEOUT
                ):
                    still_alive[server_id] = last_seen
            self._seen_servers = still_alive
            self._state.servers = {self._worker_id} | set(self._seen_servers.keys())

    async def _periodic_server_keepalive(self):
        while True:
            try:
                await self._expire_old_servers()
                self._publish(
                    opal_server_config.STATISTICS_SERVER_KEEPALIVE_CHANNEL,
                    ServerKeepalive(worker_id=self._worker_id).dict(),
                )
                await asyncio.sleep(
                    float(opal_server_config.STATISTICS_SERVER_KEEPALIVE_TIMEOUT) / 2
                )
            except asyncio.CancelledError:
                logger.debug("Statistics: periodic server keepalive cancelled")
                return
            except Exception as e:
                logger.exception("Statistics: periodic server keepalive failed")
                logger.exception("Statistics: periodic server keepalive failed")

    def _publish(self, channel: str, message: Any):
        self._publish_tasks.add_task(self._endpoint.publish([channel], message))

    async def run(self):
        """Subscribe to two channels to be able to sync add and delete of
        clients."""
        await self._endpoint.subscribe(
            [opal_server_config.STATISTICS_WAKEUP_CHANNEL],
            self._receive_other_worker_wakeup_message,
        )
        await self._endpoint.subscribe(
            [opal_server_config.STATISTICS_STATE_SYNC_CHANNEL],
            self._receive_other_worker_synced_state,
        )
        await self._endpoint.subscribe(
            [opal_server_config.STATISTICS_SERVER_KEEPALIVE_CHANNEL],
            self._receive_other_worker_keepalive_message,
        )
        await self._endpoint.subscribe(
            [opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL], self._add_client
        )
        await self._endpoint.subscribe(
            [opal_common_config.STATISTICS_REMOVE_CLIENT_CHANNEL],
            self._sync_remove_client,
        )

        # wait before publishing the wakeup message, due to the fact we are
        # counting on the broadcaster to listen and to replicate the message
        # to the other workers / server nodes in the networks.
        # However, since broadcaster is using asyncio.create_task(), there is a
        # race condition that is mitigated by this asyncio.sleep() call.
        await asyncio.sleep(SLEEP_TIME_FOR_BROADCASTER_READER_TO_START)
        # Let all the other opal servers know that new opal server started
        logger.info(f"sending stats wakeup message: {self._worker_id}")
        self._publish(
            opal_server_config.STATISTICS_WAKEUP_CHANNEL,
            SyncRequest(requesting_worker_id=self._worker_id).dict(),
        )
        self._periodic_keepalive_task = asyncio.create_task(
            self._periodic_server_keepalive()
        )

    async def stop(self):
        if self._periodic_keepalive_task:
            self._periodic_keepalive_task.cancel()
            await self._periodic_keepalive_task
            self._periodic_keepalive_task = None

    async def _sync_remove_client(self, subscription: Subscription, rpc_id: str):
        """Helper function to recall remove client in all servers.

        Args:
            subscription (Subscription): not used, we get it from callbacks.
            rpc_id (str): channel id of rpc channel used as identifier to client id
        """

        await self.remove_client(rpc_id=rpc_id, topics=[], publish=False)

    async def _receive_other_worker_wakeup_message(
        self, subscription: Subscription, sync_request: dict
    ):
        """Callback when new server wakes up and requests our statistics state.

        Sends state only if we have state of our own and another
        response to that request was not already received. Always reply
        with hello message to refresh the "workers" state of other
        servers.
        """
        try:
            request = SyncRequest(**sync_request)
        except pydantic.ValidationError as e:
            logger.warning(
                f"Got invalid statistics sync request from another server, error: {repr(e)}"
            )
            return

        if self._worker_id == request.requesting_worker_id:
            # skip my own requests
            logger.debug(
                f"IGNORING my own stats wakeup message: {request.requesting_worker_id}"
            )
            return

        logger.debug(f"received stats wakeup message: {request.requesting_worker_id}")

        if len(self._state.clients):
            # wait random time in order to reduce the number of messages sent by all the other opal servers
            await asyncio.sleep(uniform(MIN_TIME_TO_WAIT, MAX_TIME_TO_WAIT))
            # if didn't get any other message it means that this server is the first one to pass the sleep
            if request.requesting_worker_id not in self._received_sync_messages:
                logger.info(
                    f"[{request.requesting_worker_id}] respond with my own stats"
                )
                self._publish(
                    opal_server_config.STATISTICS_STATE_SYNC_CHANNEL,
                    SyncResponse(
                        requesting_worker_id=request.requesting_worker_id,
                        clients=self._state.clients,
                        rpc_id_to_client_id=self._rpc_id_to_client_id,
                    ).dict(),
                )

    async def _receive_other_worker_synced_state(
        self, subscription: Subscription, sync_response: dict
    ):
        """Callback when another server sends us it's statistics data as a
        response to a sync request.

        Args:
            subscription (Subscription): not used, we get it from callbacks.
            rpc_id (Dict[str, List[ChannelStats]]): state from remote server
        """
        try:
            response = SyncResponse(**sync_response)
        except pydantic.ValidationError as e:
            logger.warning(
                f"Got invalid statistics sync response from another server, error: {repr(e)}"
            )
            return

        async with self._lock:
            self._received_sync_messages.add(response.requesting_worker_id)

            # update my state only if this server don't have a state
            if not len(self._state.clients) and not self._synced_after_wakeup.is_set():
                logger.info(f"[{response.requesting_worker_id}] applying server stats")
                self._state.clients = response.clients
                self._rpc_id_to_client_id = response.rpc_id_to_client_id
                self._synced_after_wakeup.set()

    async def _receive_other_worker_keepalive_message(
        self, subscription: Subscription, keepalive_message: dict
    ):
        async with self._lock:
            self._seen_servers[keepalive_message["worker_id"]] = datetime.now()
            self._state.servers.add(keepalive_message["worker_id"])

    async def _add_client(self, subscription: Subscription, stats_message: dict):
        """Add client record to statistics state.

        Args:
            subscription (Subscription): not used, we get it from callbacks.
            stat_msg (ChannelStats): statistics data for channel, rpc_id - channel identifier; client_id - client identifier
        """
        try:
            stats = ChannelStats(**stats_message)
        except pydantic.ValidationError as e:
            logger.warning(
                f"Got invalid statistics message from client, error: {repr(e)}"
            )
            return
        try:
            client_id = stats.client_id
            rpc_id = stats.rpc_id
            logger.info(
                "Set client statistics {client_id} on channel {rpc_id} with {topics}",
                client_id=client_id,
                rpc_id=rpc_id,
                topics=", ".join(stats.topics),
            )
            async with self._lock:
                self._rpc_id_to_client_id[rpc_id] = client_id
                if client_id in self._state.clients:
                    # Limiting the number of channels per client to avoid memory issues if client opens too many channels
                    if (
                        len(self._state.clients[client_id])
                        < opal_server_config.MAX_CHANNELS_PER_CLIENT
                    ):
                        self._state.clients[client_id].append(stats)
                    else:
                        logger.warning(
                            f"Client '{client_id}' reached the maximum number of open RPC channels"
                        )
                else:
                    self._state.clients[client_id] = [stats]
        except Exception as err:
            logger.exception("Add client to server statistics failed")

    async def remove_client(self, rpc_id: str, topics: TopicList, publish=True):
        """Remove client record from statistics state.

        Args:
            rpc_id (str): channel id of rpc channel used as identifier to client id
            topics (TopicList): not used, we get it from callbacks.
            publish (bool): used to stop republish cycle
        """
        if rpc_id not in self._rpc_id_to_client_id:
            logger.debug(
                f"Statistics.remove_client() got unknown rpc id: {rpc_id} (probably broadcaster)"
            )
            return

        try:
            logger.info("Trying to remove {rpc_id} from statistics", rpc_id=rpc_id)
            client_id = self._rpc_id_to_client_id[rpc_id]
            for index, stats in enumerate(self._state.clients[client_id]):
                if stats.rpc_id == rpc_id:
                    async with self._lock:
                        # remove the stats record matching the removed rpc id
                        del self._state.clients[client_id][index]
                        # remove the connection between rpc and client, once we removed it from state
                        del self._rpc_id_to_client_id[rpc_id]
                        # if no client records left in state remove the client entry
                        if not len(self._state.clients[client_id]):
                            del self._state.clients[client_id]
                    break
        except Exception as err:
            logger.warning(f"Remove client from server statistics failed: {repr(err)}")
        # publish removed client so each server worker and server instance would get it
        if publish:
            logger.info(
                "Publish rpc_id={rpc_id} to be removed from statistics",
                rpc_id=rpc_id,
            )
            self._publish(
                opal_common_config.STATISTICS_REMOVE_CLIENT_CHANNEL,
                rpc_id,
            )


def init_statistics_router(stats: Optional[OpalStatistics] = None):
    """Initializes a route where a client (or any other network peer) can
    inquire what opal clients are currently connected to the server and on what
    topics are they registered.

    If the OPAL server does not have statistics enabled, the route will
    return 501 Not Implemented
    """
    router = APIRouter()

    @router.get("/statistics", response_model=ServerStats)
    async def get_statistics():
        """Route to serve server statistics."""
        if stats is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={
                    "error": "This OPAL server does not have statistics turned on."
                    + " To turn on, set this config var: OPAL_STATISTICS_ENABLED=true"
                },
            )
        logger.info("Serving statistics")
        return stats.state

    @router.get("/stats", response_model=ServerStatsBrief)
    async def get_stat_counts():
        """Route to serve only server and client instanace counts."""
        if stats is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={
                    "error": "This OPAL server does not have statistics turned on."
                    + " To turn on, set this config var: OPAL_STATISTICS_ENABLED=true"
                },
            )
        logger.info("Serving brief statistics info")
        return stats.state_brief

    return router
