import asyncio
from typing import List

from opal.common.logger import get_logger
from opal.common.git.repo_watcher import RepoWatcher


class RepoWatcherTask:
    """
    Manages the asyncio tasks of the repo watcher
    """
    def __init__(self, repo_watcher: RepoWatcher):
        self._watcher = repo_watcher
        self._logger = get_logger("opal.git.watcher.task")
        self._tasks: List[asyncio.Task] = []

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """
        starts the repo watcher and registers a failure callback to terminate gracefully
        """
        self._logger.info("Launching repo watcher")
        self._watcher.on_git_failed(self._fail)
        self._tasks.append(asyncio.create_task(self._watcher.run()))

    async def stop(self):
        """
        stops all repo watcher tasks
        """
        self._logger.info("Stopping repo watcher")
        await self._watcher.stop()
        for task in self._tasks:
            task.cancel()
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass

    def trigger(self):
        """
        triggers the repo watcher from outside to check for changes (git pull)
        """
        self._tasks.append(asyncio.create_task(self._watcher.check_for_changes()))

    async def _fail(self, exc: Exception):
        """
        called when the watcher fails, and stops all tasks gracefully
        """
        self._logger.error("watcher failed with exception", watcher_exception=exc)
        await self.stop()