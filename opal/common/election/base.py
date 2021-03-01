import asyncio

from typing import Callable, Coroutine, List

ElectionDecisionCallback = Callable[[bool], Coroutine]

class LeaderElectionBase:
    """
    Leader election algorithm for a distributed system.

    When we want only one process to do something (like publishing certain topics)
    all processes can run this algorithm and only one is guaranteed to be elected as leader.
    """
    def __init__(self):
        self._on_decision_callbacks: List[ElectionDecisionCallback] = []

    def on_desicion(self, callback: ElectionDecisionCallback):
        self._on_decision_callbacks.append(callback)

    async def _trigger_callbacks(self, decision: bool):
        return await asyncio.gather(*(
            callback(decision) for callback in self._on_decision_callbacks
        ))

    async def elect(self) -> bool:
        """
        returns true if the calling process was elected leader.
        """
        decision = await self._elect()
        await self._trigger_callbacks(decision)
        return decision

    async def _elect(self) -> bool:
        """
        election method, to be implemented by child class.
        """
        raise NotImplementedError()