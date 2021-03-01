class LeaderElectionBase:
    """
    Leader election algorithm for a distributed system.

    When we want only one process to do something (like publishing certain topics)
    all processes can run this algorithm and only one is guaranteed to be elected as leader.
    """
    def elect(self) -> bool:
        """
        returns true if the calling process was elected leader.
        """
        raise NotImplementedError()