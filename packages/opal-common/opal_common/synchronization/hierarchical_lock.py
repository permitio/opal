import asyncio
from contextlib import asynccontextmanager
from typing import Set

from loguru import logger


class HierarchicalLock:
    """A hierarchical lock for asyncio.

    - If a path is locked, no ancestor or descendant path can be locked.
    - Conversely, if a child path is locked, the parent path cannot be locked
      until all child paths are released.
    """

    def __init__(self):
        # locked_paths: set of currently locked string paths
        self._locked_paths: Set[str] = set()
        # Map of tasks to their acquired locks for re-entrant protection
        self._task_locks: dict[asyncio.Task, Set[str]] = {}
        # Internal lock for synchronizing access to locked_paths
        self._lock = asyncio.Lock()
        # Condition to wake up tasks when a path is released
        self._cond = asyncio.Condition(self._lock)

    @staticmethod
    def _is_conflicting(p1: str, p2: str) -> bool:
        """Check if two paths conflict with each other."""
        return p1 == p2 or p1.startswith(p2) or p2.startswith(p1)

    async def acquire(self, path: str):
        """Acquire the lock for the given hierarchical path.

        If an ancestor or descendant path is locked, this will wait
        until it is released.
        """
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("acquire() must be called from within a task.")

        async with self._lock:
            # Prevent re-entrant locking by the same task
            if path in self._task_locks.get(task, set()):
                raise RuntimeError(f"Task {task} cannot re-acquire lock on '{path}'.")

            # Wait until there is no conflict with existing locked paths
            while any(self._is_conflicting(path, lp) for lp in self._locked_paths):
                logger.debug(
                    f"Found conflicting path with {path!r}, waiting for release to check again..."
                )
                # Condition.wait() releases the lock and waits for notify_all()
                await self._cond.wait()

            # Acquire the path
            self._locked_paths.add(path)
            if task not in self._task_locks:
                self._task_locks[task] = set()
            self._task_locks[task].add(path)
            logger.debug("Acquired lock for path: {}", path)

    async def release(self, path: str):
        """Release the lock for the given path and notify waiting tasks."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("release() must be called from within a task.")

        async with self._lock:
            if path not in self._locked_paths:
                raise RuntimeError(f"Cannot release path '{path}' that is not locked.")

            if path not in self._task_locks.get(task, set()):
                raise RuntimeError(
                    f"Task {task} cannot release lock on '{path}' it does not hold."
                )

            # Remove the path from locked paths and task locks
            self._locked_paths.remove(path)
            self._task_locks[task].remove(path)
            if not self._task_locks[task]:
                del self._task_locks[task]

            # Notify all tasks that something was released
            self._cond.notify_all()
            logger.debug("Released lock for path: {}", path)

    @asynccontextmanager
    async def lock(self, path: str) -> "HierarchicalLock":
        """Acquire the lock for the given path and return a context manager."""
        await self.acquire(path)
        try:
            yield self
        finally:
            await self.release(path)
