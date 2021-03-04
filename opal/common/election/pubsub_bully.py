import asyncio

from uuid import uuid4
from typing import Optional, List, Tuple

from fastapi_websocket_pubsub import PubSubClient, Topic

from opal.common.election.base import LeaderElectionBase
from opal.common.logger import get_logger

ELECTION_TOPIC = "leader_election"

class PubSubBullyLeaderElection(LeaderElectionBase):
    """
    A "bully" election algorithm to elect a leader (coordinator) process
    @see https://en.wikipedia.org/wiki/Bully_algorithm

    Each process selects a random number (UUID) and publishes it to a shared
    broadcast channel. It also listens on the broadcast channel and keep a
    record of all the candidates ids (including its own). After a predefined
    timeout, each participant locally picks the candidate with the highest
    number.

    Usage:
      - call on_decision(callback) to register a callback (optional)
      - call await self.elect() to run the algorithm
    """
    def __init__(
        self,
        server_uri: str,
        extra_headers: Optional[List[Tuple[str, str]]] = None,
        wait_time_for_publish: float = 1,
        wait_time_for_decision: float = 1,
    ):
        """[summary]

        Args:
            server_uri (str): the URI of the pub sub server we subscribe to
            extra_headers (dict): optional headers for the websocket client
                http request (@see PubSubClient docs)
            wait_time_for_publish (float): wait time in seconds *before*
                publishing own number, intended to make sure all participants
                are up and listening on the broadcast channel.
            wait_time_for_decision (float): wait time in seconds *after*
                publishing own number, intended to make sure all participants
                received all the messages from all other partipicants and are
                ready to pick the leader.
        """
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
        the election method we use, see the class description for details.
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