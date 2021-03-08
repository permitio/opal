import asyncio

from typing import Callable, Coroutine, List

ElectionDecisionCallback = Callable[[bool], Coroutine]

class LeaderElectionBase:
    """
    Base class for leader election algorithms (for a distributed system).

    When we want only one process to do something (like publishing certain topics)
    all processes can run this algorithm and only one is guaranteed to be elected as leader.

    Usage:
      - override self._elect to implement the election algorithm
      - call on_decision(callback) to register a callback (optional)
      - call await self.elect() to run the algorithm
    """
    def __init__(self):
        self._on_decision_callbacks: List[ElectionDecisionCallback] = []

    def on_decision(self, callback: ElectionDecisionCallback):
        """
        register a callback on the election result.

        This is *optional*; one can also await on self.elect(), but for use
        cases when you want to run the election in a seperate asyncio Task
        or in a thread there is also the option to use the callback.

        It is possible to register more than one callback.

        Args:
            callback (ElectionDecisionCallback): callback to run on the result
        """
        self._on_decision_callbacks.append(callback)

    async def _trigger_callbacks(self, decision: bool):
        """
        triggers all the callbacks with the election result.
        """
        return await asyncio.gather(*(
            callback(decision) for callback in self._on_decision_callbacks
        ))

    async def elect(self) -> bool:
        """
        Runs the election algorithm.

        Returns:
            True if the calling process was elected leader. False otherwise.

        triggers any callbacks that were registered on the result.
        """
        decision = await self._elect()
        await self._trigger_callbacks(decision)
        return decision

    async def _elect(self) -> bool:
        """
        election method, to be implemented by child class.
        """
        raise NotImplementedError()