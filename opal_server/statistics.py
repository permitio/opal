import asyncio
from datetime import datetime
from typing import Dict, List
from fastapi import APIRouter
from fastapi.params import Depends
from fastapi_websocket_pubsub.event_notifier import Subscription, TopicList
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from pydantic.main import BaseModel

from opal_common.config import opal_common_config
from opal_common.logger import get_logger
from opal_server.config import opal_server_config


class Statistics(BaseModel):
    rpc_id: str
    client_id: str
    topics: TopicList


logger = get_logger("opal.statistics")


class OpalStatistics():
    """
    manage opal server statistics

    Args:
        endpoint:
        The pub/sub server endpoint that allowes us to subscribe to the stats channel on the server side
    """
    def __init__(self, endpoint):
        # state: Dict[str, List[Statistics]]
        # The state is built in this way so it will be easy to understand how much OPAL clients (vs. rpc clients)
        # you have connected to your OPAL server and to help merge client lists between servers.
        # The state is keyed by unique client id (A unique id that each opal client can set in env var `OPAL_CLIENT_STAT_ID`)
        self.state: Dict[str, List[Statistics]] = {}
        self.endpoint: PubSubEndpoint = endpoint

        # rpc_id_to_client_id:
        # dict to help us get client id without another loop
        self.rpc_id_to_client_id: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self.uptime = datetime.utcnow()
        # uptime for this statistics instance
        self.state['uptime'] = self.uptime

    async def run(self):
        """
        subscribe to two channels to be able to sync add and delete of clients
        """

        await self.endpoint.subscribe([opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL], self._add_client)
        await self.endpoint.subscribe([opal_common_config.STATISTICS_REMOVE_CLIENT_CHANNEL], self._sync_remove_client)

    async def _sync_remove_client(self, subscription: Subscription, rpc_id: str):
        """
        helper function to recall remove client in all servers

        Args:
            subscription (Subscription): not used, we get it from callbacks.
            rpc_id (str): channel id of rpc channel used as identifier to client id
        """

        await self.remove_client(rpc_id=rpc_id, topics=[], publish=False)

    async def _add_client(self, subscription: Subscription, stat_msg: Statistics):
        """
        add client record to statistics state

        Args:
            subscription (Subscription): not used, we get it from callbacks.
            stat_msg (Statistics): statistics data, rpc_id - channel identifier; client_id - client identifier
        """
        try:
            client_id = stat_msg['client_id']
            logger.info("Set client statistics {client_id} on channel {rpc_id} with {topics}", client_id=stat_msg['client_id'], rpc_id=stat_msg['rpc_id'], topics=', '.join(stat_msg['topics']))
            async with self._lock:
                self.rpc_id_to_client_id[stat_msg['rpc_id']] = client_id
                if client_id in self.state:
                    # Limiting the number of channels per client to avoid memory issues if client opens to many channels
                    if len(self.state[client_id]) < opal_server_config.MAX_CHANNELS_PER_CLIENT:
                        self.state[client_id].append(stat_msg)
                    else:
                        logger.warning("Client {client_id} reached the max of channels, might be a issue", client_id=client_id)
                else:
                    self.state[client_id] = [stat_msg]
        except Exception as err:
            logger.exception("Add client to server statistics failed")

    async def remove_client(self, rpc_id: str, topics: TopicList, publish=True):
        """
        remove client record from statistics state

        Args:
            rpc_id (str): channel id of rpc channel used as identifier to client id
            topics (TopicList): not used, we get it from callbacks.
            publish (bool): used to stop republish cycle
        """
        try:
            logger.info("Trying to remove {rpc_id} from statistics", rpc_id=rpc_id)
            if rpc_id in self.rpc_id_to_client_id:
                for idx, stats in enumerate(self.state[self.rpc_id_to_client_id[rpc_id]]):
                    if stats['rpc_id'] == rpc_id:
                        async with self._lock:
                            del self.state[self.rpc_id_to_client_id[rpc_id]][idx]
                            # save the client id if we will need it to delete client record from self.state
                            tmp_client_from_rpc_id = self.rpc_id_to_client_id[rpc_id]
                            # remove the connection between rpc and client, once we removed it from state
                            del self.rpc_id_to_client_id[rpc_id]
                            # if no client records left in state remove the client entry
                            if not len(self.state[tmp_client_from_rpc_id]):
                                del self.state[tmp_client_from_rpc_id]
        except Exception as err:
            logger.exception("Remove client from server statistics failed")
        # publish removed client so each server worker and server instance would get it
        if publish:
            logger.info("Publish rpc_id={rpc_id} to be removed from statistics", rpc_id=rpc_id)
            asyncio.create_task(self.endpoint.publish([opal_common_config.STATISTICS_REMOVE_CLIENT_CHANNEL], rpc_id))

    def init_statistics_router(self):
        router = APIRouter()

        @router.get('/statistics')
        async def get_statistics(self):
            """
            Route to serve server statistics
            """
            logger.info("Serving statistics")
            return self.state

        return router
