import asyncio
import glob
import hashlib
import logging
import os
import threading
from typing import Coroutine, Dict, List, Tuple

import aiohttp


def get_filepaths_with_glob(root_path: str, file_regex: str):
    return glob.glob(os.path.join(root_path, file_regex))


def hash_file(tmp_file_path):
    BUF_SIZE = 65536  # lets read stuff in 64kb chunks!
    sha256_hash = hashlib.sha256()
    with open(tmp_file_path, "rb") as file:
        while True:
            data = file.read(BUF_SIZE)
            if not data:
                break
            sha256_hash.update(data)
    return sha256_hash.hexdigest()


async def throw_if_bad_status_code(
    response: aiohttp.ClientResponse, expected: List[int], logger=None
) -> aiohttp.ClientResponse:
    if response.status in expected:
        return response

    # else, bad status code
    details = await response.json()
    if logger:
        logger.warning(
            "Unexpected response code {status}: {details}",
            status=response.status,
            details=details,
        )
    raise ValueError(
        f"unexpected response code while fetching bundle: {response.status}"
    )


def tuple_to_dict(tup: Tuple[str, str]) -> Dict[str, str]:
    return dict([tup])


def get_authorization_header(token: str) -> Tuple[str, str]:
    return "Authorization", f"Bearer {token}"


def sorted_list_from_set(s: set) -> list:
    l = list(s)
    l.sort()
    return l


async def thread_worker(queue: asyncio.Queue, logger: logging.Logger):
    """The worker task is *running and then awaiting* a coroutine that was
    scheduled on the thread's async loop from *OUTSIDE* (i.e: from another
    thread).

    Args:
        queue (asyncio.Queue): The Queue
        engine (BaseFetchingEngine): The engine itself
    """
    while True:
        # get the next coroutine scheduled on the thread's queue
        # this may block until another coroutine is scheduled
        coro: Coroutine = await queue.get()

        try:
            # await on the coroutine and possibly block *this* worker
            await coro
        except Exception as err:
            logger.exception(f"Scheduled coroutine - {coro} failed")
        finally:
            # Notify the queue that the "work item" has been processed.
            queue.task_done()


class AsyncioEventLoopThread(threading.Thread):
    """This class enable a sync (or async) program to run (another) asyncio
    event loop in a separate thread without blocking the main thread or
    interfering with the main thread's asyncio loop if such exists.

    usage:
    t = AsyncioEventLoopThread()

    # not yet running
    t.create_task(coroutine1())
    t.create_task(coroutine2())

    # will start the event loop and all scheduled tasks
    t.start()
    """

    DEFAULT_WORKER_COUNT = 5

    def __init__(self, *args, loop=None, worker_count=DEFAULT_WORKER_COUNT, **kwargs):
        super().__init__(*args, **kwargs)
        self.daemon = True
        self.running = False
        self.loop = loop or asyncio.new_event_loop()
        # the thread is assigned a main logger bearing its name
        self.logger = logging.getLogger(self.name)
        # The internal task queue
        self._queue = asyncio.Queue(loop=self.loop)
        # Worker working the queue
        self._tasks = []

        # create worker tasks
        for _ in range(worker_count):
            self._create_worker()

    def run(self):
        """called by the default threading.Thread.start() method.

        runs the main activity of the thread, which in our case is
        simply running the asyncio loop until it stop.
        """
        self.running = True
        # does not return (thread will keep running) until loop.stop() is called
        if not self.loop.is_running():
            self.loop.run_forever()

    def stop(self):
        """Stops the thread.

        (Stop the async loop running on the thread and then joins the
        main thread).
        """
        self.run_coro(self._shutdown())  # will block until _shutdown() returns
        self.join()  # will block until run() exits
        self.running = False

    def _create_worker(self) -> asyncio.Task:
        """Create an asyncio worker task to work the thread's queue."""
        task = self.loop.create_task(thread_worker(self._queue, self.logger))
        self._tasks.append(task)
        return task

    async def _shutdown(self):
        """Cancel and wait on the thread's async tasks."""
        tasks = [
            t
            for t in asyncio.all_tasks(loop=self.loop)
            if t is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        # Wait until all tasks are cancelled.
        await asyncio.gather(*tasks, return_exceptions=True)
        # stop the thread async loop
        self.loop.stop()

    def create_task(self, coro: Coroutine):
        """Creates a task on the thread's asyncio loop *without* waiting for it
        to finish. This is intended to be called from the parent thread as a
        set-and-forget.

        the scheduled coroutine is put on the thread's queue and is
        consumed by one of the thread workers.
        """

        async def _schedule_task():
            """since the queue is infinite, queue.put() will not block."""
            await self._queue.put(coro)

        # the asyncio loop might not be running yet (if the thread was
        # not yet started), therefore we do not block on the result.
        return asyncio.run_coroutine_threadsafe(_schedule_task(), loop=self.loop)

    def run_coro(self, coro: Coroutine):
        """can be called from the main thread, but will run the coroutine on
        the event loop thread.

        the main thread will block until a result is returned. calling
        run_coro() is thread-safe.
        """
        return asyncio.run_coroutine_threadsafe(coro, loop=self.loop).result()
