import asyncio
import logging
from typing import Dict, List
from fastapi_websocket_pubsub.event_notifier import TopicList
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
        client_id: topics
    '''
    def __init__(self, endpoint):
        self.state: Dict[str, Statistics] = {}
        self.endpoint: PubSubEndpoint = endpoint
        self.id_to_client: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def run(self):
        await self.endpoint.subscribe(['stats'], self.add_client)

    async def add_client(self, subscriber_id: str, stat_msg: Statistics):
        stat = stat_msg
        stat['rpc_id'] = subscriber_id.subscriber_id
        client_id = stat_msg['uID']
        logger.info("Set client statistics {client_id} with {topics}".format(client_id=stat['rpc_id'], topics=', '.join(stat_msg['topics'])))
        with self._lock:
            self.id_to_client[stat['rpc_id']] = client_id
            if client_id in self.state:
                self.state[client_id].append(stat)
            else:
                self.state[client_id] = [stat]

    async def remove_client(self, rpc_id: str, topics):
        for topic, sub in topics.items():
            rpc_id = list(sub.keys())[0]
            if self.id_to_client[rpc_id] in self.state:
                with self._lock:
                    del self.state[self.id_to_client[rpc_id]]
                    del self.id_to_client[rpc_id]
