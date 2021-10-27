import asyncio
import logging
from typing import Dict, List
from fastapi_websocket_pubsub.event_notifier import Subscription, TopicList
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from pydantic.main import BaseModel


class Statistics(BaseModel):
    rpc_id: List[str]
    client_id: str
    topics: TopicList


logger = logging.getLogger("opal.statistics")


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
        await self.endpoint.subscribe(['stats'], self.add_client)

    async def add_client(self, subscription: Subscription, stat_msg: Statistics):
        stat = stat_msg
        stat['rpc_id'] = subscription.subscriber_id
        client_id = stat_msg['client_id']
        logger.info("Set client statistics {client_id} with {topics}".format(client_id=stat['rpc_id'], topics=', '.join(stat_msg['topics'])))
        with self._lock:
            self.rpc_id_to_client_id[stat['rpc_id']] = client_id
            if client_id in self.state:
                self.state[client_id].append(stat)
            else:
                self.state[client_id] = [stat]

    async def remove_client(self, rpc_id: str, topics: TopicList):
        for topic, sub in topics.items():
            rpc_id = list(sub.keys())[0]
            if self.rpc_id_to_client_id[rpc_id] in self.state:
                for idx, stat in enumerate(self.state[self.rpc_id_to_client_id[rpc_id]]):
                    if stat['rpc_id'] == rpc_id:
                        with self._lock:
                            del self.state[self.rpc_id_to_client_id[rpc_id]][idx]
                            if not len(self.state[self.rpc_id_to_client_id[rpc_id]]):
                                del self.state[self.rpc_id_to_client_id[rpc_id]]
                                del self.rpc_id_to_client_id[rpc_id]
