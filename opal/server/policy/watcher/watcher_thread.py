from opal.common.logger import get_logger
from opal.common.git.repo_watcher import RepoWatcher
from opal.common.utils import AsyncioEventLoopThread

logger = get_logger("opal.git.watcher.thread")

class RepoWatcherThread:
    """
    runs a repo watcher in a separate thread (with separate asyncio loop).
    """
    def __init__(self, repo_watcher: RepoWatcher):
        self._thread = AsyncioEventLoopThread(name="RepoWatcherThread")
        self._watcher = repo_watcher

    def start(self):
        """
        starts the repo watcher on a new thread
        """
        logger.info("Launching repo watcher")
        self._watcher.on_git_failed(self._fail)
        self._thread.create_task(self._watcher.run())
        self._thread.start()

    def stop(self):
        """
        stops the repo watcher thread.
        """
        logger.info("Stopping repo watcher")
        self._thread.stop()

    async def _fail(self, exc: Exception):
        """
        called when the watcher fails, and stops the thread.
        """
        logger.error("watcher failed with exception", watcher_exception=exc)
        self.stop()

    def trigger(self):
        """
        triggers a git pull and check for update inside the watcher thread.
        """
        self._thread.create_task(self._watcher.check_for_changes())
