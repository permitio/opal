import os
import psutil

from typing import List
from psutil import Process

from opal.common.election.base import LeaderElectionBase
from opal.common.logger import get_logger

class UvicornWorkerPidLeaderElection(LeaderElectionBase):
    """
    A very simple leader election algorithm for uvicorn workers.
    all workers are spawned as subprocesses of the uvicorn monitor
    process, therefore they are all sibling processes.

    The algorithm (which is a form of a "Bully algorithm") simply picks
    the worker with the highest process id (pid).
    @see https://en.wikipedia.org/wiki/Bully_algorithm

    This algorithm should be called after all workers processes are up
    and will only work for workers running on the same machine.

    Usage:
      - call on_decision(callback) to register a callback (optional)
      - call await self.elect() to run the algorithm
    """
    def __init__(self):
        self._my_pid = os.getpid()
        self._logger = get_logger(f"election.candidate.{self._my_pid}")
        super().__init__()

    async def _elect(self) -> bool:
        """
        the election method we use, see the class description for details.
        returns true if the calling process was elected leader.
        """
        my_process = psutil.Process(self._my_pid)
        sibling_processes: List[Process] = my_process.parent().children()
        sibling_pids = [sibling.pid for sibling in sibling_processes]
        sibling_pids.sort()
        leader_pid = sibling_pids[-1] # highest pid
        if leader_pid == self._my_pid:
            self._logger.info("elected", leader=leader_pid, siblings=sibling_pids)
            return True
        else:
            self._logger.info("NOT elected", leader=leader_pid, siblings=sibling_pids)
            return False