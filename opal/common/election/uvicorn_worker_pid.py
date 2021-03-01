import os
import psutil

from typing import List
from psutil import Process

from opal.common.election.base import LeaderElectionBase
from opal.common.logger import get_logger

class UvicornWorkerPidLeaderElection(LeaderElectionBase):
    """
    a very simple leader election algorithm for uvicorn workers.
    all workers are spawned as subprocesses of the uvicorn monitor,
    therefore they are all sibling processes.

    The algorithm (which is a form of a Bully algorithm) simply picks
    the worker with the highest process id (pid).

    This algorithm should be called after all workers processes are up
    and will only work for one execution of uvicorn (same machine).
    """
    def __init__(self):
        self._my_pid = os.getpid()
        self._logger = get_logger(f"opal.worker.{self._my_pid}")

    def elect(self) -> bool:
        """
        returns true if the calling process was elected leader.
        """
        my_process = psutil.Process(self._my_pid)
        sibling_processes: List[Process] = my_process.parent().children()
        sibling_pids = [sibling.pid for sibling in sibling_processes]
        sibling_pids.sort()
        leader_pid = sibling_pids[-1] # highest pid
        if leader_pid == self._my_pid:
            self._logger.info("leader election: elected", leader=leader_pid, siblings=sibling_pids)
            return True
        else:
            self._logger.info("leader election: NOT elected", leader=leader_pid, siblings=sibling_pids)
            return False