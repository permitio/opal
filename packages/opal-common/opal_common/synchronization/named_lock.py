import asyncio
import fcntl
import os
import time
from typing import Optional

from opal_common.logger import logger

DEFAULT_LOCK_ATTEMPT_INTERVAL = 5.0


class NamedLock:
    """creates a a file-lock (can be a normal file or a named pipe / fifo), and
    exposes a context manager to try to acquire the lock asyncronously."""

    def __init__(
        self, path: str, attempt_interval: float = DEFAULT_LOCK_ATTEMPT_INTERVAL
    ):
        self._lock_file: str = path
        self._lock_file_fd = None
        self._attempt_interval = attempt_interval

    async def __aenter__(self):
        """using the lock as a context manager will try to acquire the lock
        until successful (without timeout)"""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """releases the lock when exiting the lock context."""
        await self.release()

    async def acquire(self, timeout: Optional[int] = None):
        """tries to acquire the lock.

        if unsuccessful, will sleep and then try again after the attempt
        interval. an optional timeout can be provided to give up before
        acquiring the lock, in case we reach timeout, function throws
        TimeoutError.
        """
        logger.debug(
            "[{pid}] trying to acquire lock (lock={lock})",
            pid=os.getpid(),
            lock=self._lock_file,
        )
        start_time = time.time()
        while True:
            if self._acquire():
                logger.debug(
                    "[{pid}] lock acquired! (lock={lock})",
                    pid=os.getpid(),
                    lock=self._lock_file,
                )
                break
            await asyncio.sleep(self._attempt_interval)
            # potentially give up due to timeout (if timeout is set)
            if timeout is not None and time.time() - start_time > timeout:
                raise TimeoutError("could not acquire lock")

    async def release(self):
        """releases the lock."""
        logger.debug(
            "[{pid}] releasing lock (lock={lock})",
            pid=os.getpid(),
            lock=self._lock_file,
        )
        fd = self._lock_file_fd
        self._lock_file_fd = None
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    @property
    def is_locked(self):
        """True, if the object holds the file lock."""
        return self._lock_file_fd is not None

    def _acquire(self) -> bool:
        """tries to acquire the lock, returns immediately regardless of
        success.

        returns True if lock was acquired successfully, False otherwise.
        """
        fd = os.open(self._lock_file, os.O_RDWR | os.O_CREAT | os.O_TRUNC)

        # try to acquire the lock, returns immediately
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            os.close(fd)
        else:
            self._lock_file_fd = fd
        return self.is_locked
