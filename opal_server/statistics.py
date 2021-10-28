import asyncio
import json
from typing import Dict, List
from fastapi import APIRouter
from fastapi.params import Depends
from fastapi_websocket_pubsub.event_notifier import Subscription, TopicList
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from pydantic.main import BaseModel
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.config import opal_common_config
from opal_common.logger import get_logger
from opal_server.config import opal_server_config


class Statistics(BaseModel):
    rpc_id: str
    client_id: str
    topics: TopicList


logger = get_logger("opal.statistics")


class OpalStatistics():
    '''
    manage opal server statistics

    state:
        client_id(A uniq id that each opal client can set in env var `OPAL_CLIENT_STAT_ID`): List[Statistics]
        the state is built in this way so it will be easy to understand how much real clients you have connected to your server
        and to help merge client lists between servers `OPAL_CLIENT_STAT_ID` should be uniq
    endpoint:
        Pubsub end point to subscribe to stats channel
    rpc_id_to_client_id:
        dict to help us get client id without another loop

    '''
    def __init__(self, endpoint):
        self.state: Dict[str, List[Statistics]] = {}
        self.endpoint: PubSubEndpoint = endpoint
        self.rpc_id_to_client_id: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def run(self):
        await self.endpoint.subscribe([opal_common_config.STATISTICS_ADD_CLIENT_CHANNEL], self.add_client)
        await self.endpoint.subscribe([opal_common_config.STATISTICS_REMOVE_CLIENT_CHANNEL], self.sync_remove_client)

    async def sync_remove_client(self, subscription: Subscription, rpc_id: str):
        await self.remove_client(rpc_id=rpc_id, topics=[], publish=False)

    async def add_client(self, subscription: Subscription, stat_msg: Statistics):
        try:
            client_id = stat_msg['client_id']
            logger.info("Set client statistics {client_id} with {topics}", client_id=stat_msg['client_id'], topics=', '.join(stat_msg['topics']))
            async with self._lock:
                self.rpc_id_to_client_id[stat_msg['rpc_id']] = client_id
                if client_id in self.state:
                    self.state[client_id].append(stat_msg)
                else:
                    self.state[client_id] = [stat_msg]
        except Exception as err:
            logger.exception("Add client to server statistics failed")

    async def remove_client(self, rpc_id: str, topics: TopicList, publish=True):
        try:
            logger.info("Trying to remove {rpc_id} from statistics", rpc_id=rpc_id)
            if rpc_id in self.rpc_id_to_client_id:
                for idx, stats in enumerate(self.state[self.rpc_id_to_client_id[rpc_id]]):
                    if stats['rpc_id'] == rpc_id:
                        del self.state[self.rpc_id_to_client_id[rpc_id]][idx]
                        if not len(self.state[self.rpc_id_to_client_id[rpc_id]]):
                            del self.rpc_id_to_client_id[rpc_id]
                            del self.state[self.rpc_id_to_client_id[rpc_id]]
        except Exception as err:
            logger.exception("Remove client from server statistics failed")
        if publish:
            logger.info("Publish rpc_id={rpc_id} to be removed from statistics", rpc_id=rpc_id)
            asyncio.create_task(self.endpoint.publish([opal_common_config.STATISTICS_REMOVE_CLIENT_CHANNEL], rpc_id))

    def init_statistics_router(self, authenticator: JWTAuthenticator):
        router = APIRouter()

        @router.get('/statistics') #bsd check auth
        async def get_statistics():
            """
            Route to serve server statistics
            """
            logger.info("Serving statistics")
            return self.state

        return router
