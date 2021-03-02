import asyncio

from uuid import uuid4
from typing import Optional, List, Tuple

from fastapi_websocket_pubsub import PubSubClient, Topic

from opal.common.election.base import LeaderElectionBase
from opal.common.logger import get_logger

ELECTION_TOPIC = "leader_election"

class PubSubBullyLeaderElection(LeaderElectionBase):
    """
    a bully election algorithm, each process selects a random number (UUID)
    and publishes it to a shared channel. all participants also subscribe to
    the shared channel, after a timeout, all participants pick the candidate
    with the highest number.

    Communication is transmitted over the PubSubEndpoint broadcast channel.
    """
    def __init__(
        self,
        server_uri: str,
        extra_headers: Optional[List[Tuple[str, str]]] = None,
        wait_time_for_publish: float = 1,
        wait_time_for_decision: float = 1,
    ):
        self._server_uri = server_uri
        self._extra_headers = extra_headers
        self._wait_time_for_publish = wait_time_for_publish
        self._wait_time_for_decision = wait_time_for_decision
        self._my_id = uuid4().hex
        self._known_candidates = set()
        self._known_candidates.add(self._my_id)
        self._logger = get_logger(f"election.candidate.{self._my_id}")
        super().__init__()

    async def _elect(self) -> bool:
        """
        returns true if the calling process was elected leader.
        """
        async with PubSubClient(extra_headers=self._extra_headers) as client:
            async def on_new_candidate(data: str, topic: Topic):
                self._known_candidates.add(data)

            # start client
            client.subscribe(ELECTION_TOPIC, on_new_candidate)
            client.start_client(self._server_uri)

            # await for all other processes to go up and subscribe
            await asyncio.gather(
                client.wait_until_ready(),
                asyncio.sleep(self._wait_time_for_publish)
            )

            # publish own random id
            await client.publish(ELECTION_TOPIC, data=self._my_id)

            # wait for all candidates to finish publishing their id
            await asyncio.sleep(self._wait_time_for_decision)

            leader_id = max(self._known_candidates)
            if leader_id == self._my_id:
                self._logger.info("elected", leader=leader_id, candidates=list(self._known_candidates))
                return True
            else:
                self._logger.info("NOT elected", leader=leader_id, candidates=list(self._known_candidates))
                return False