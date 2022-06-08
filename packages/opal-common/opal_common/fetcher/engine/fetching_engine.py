import asyncio
import uuid
from typing import Coroutine, Dict, List, Union

from ..events import FetcherConfig, FetchEvent
from ..fetch_provider import BaseFetchProvider
from ..fetcher_register import FetcherRegister
from ..logger import get_logger
from .base_fetching_engine import BaseFetchingEngine
from .core_callbacks import OnFetchFailureCallback
from .fetch_worker import fetch_worker

logger = get_logger("engine")


class FetchingEngine(BaseFetchingEngine):
    """A Task queue manager for fetching events.

    - Configure with different fetcher providers - via __init__'s register_config or via self.register.register_fetcher()
    - Use queue_url() to fetch a given URL with the default FetchProvider
    - Use queue_fetch_event() to fetch data using a configured FetchProvider
    - Use with 'async with' to terminate tasks (or call self.terminate_tasks() when done)
    """

    DEFAULT_WORKER_COUNT = 5
    DEFAULT_CALLBACK_TIMEOUT = 10
    DEFAULT_ENQUEUE_TIMEOUT = 10

    @staticmethod
    def gen_uid():
        return uuid.uuid4().hex

    def __init__(
        self,
        register_config: Dict[str, BaseFetchProvider] = None,
        worker_count: int = DEFAULT_WORKER_COUNT,
        callback_timeout: int = DEFAULT_CALLBACK_TIMEOUT,
        enqueue_timeout: int = DEFAULT_ENQUEUE_TIMEOUT,
    ) -> None:
        # The internal task queue (created at start_workers)
        self._queue: asyncio.Queue = None
        # Worker working the queue
        self._tasks: List[asyncio.Task] = []
        # register of the fetch providers workers can use
        self._fetcher_register = FetcherRegister(register_config)
        # core event callback regsiters
        self._failure_handlers: List[OnFetchFailureCallback] = []
        # how many workers to run
        self._worker_count: int = worker_count
        # time in seconds before timeout on a fetch callback
        self._callback_timeout = callback_timeout
        # time in seconds before time out on adding a task to queue (when full)
        self._enqueue_timeout = enqueue_timeout

    def start_workers(self):
        if self._queue is None:
            self._queue = asyncio.Queue()
            # create worker tasks
            for _ in range(self._worker_count):
                self.create_worker()

    @property
    def register(self) -> FetcherRegister:
        return self._fetcher_register

    async def __aenter__(self):
        """Async Context manager to cancel tasks on exit."""
        self.start_workers()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc is not None:
            logger.error(
                "Error occurred within FetchingEngine context",
                exc_info=repr((exc_type, exc, tb)),
            )
        await self.terminate_workers()

    async def terminate_workers(self):
        """Cancel and wait on the internal worker tasks."""
        # Cancel our worker tasks.
        for task in self._tasks:
            task.cancel()
        # Wait until all worker tasks are cancelled.
        await asyncio.gather(*self._tasks, return_exceptions=True)
        # reset queue
        self._queue = None

    async def handle_url(self, url: str, timeout: float = None, **kwargs):
        """
        Same as self.queue_url but instead of using a callback, you can wait on this coroutine for the result as a return value
        Args:
            url (str):
            timeout (float, optional): time in seconds to wait on the queued fetch task. Defaults to self._callback_timeout.
            kwargs: additional args passed to self.queue_url

        Raises:
            asyncio.TimeoutError: if the given timeout has expired
            also - @see self.queue_fetch_event
        """
        timeout = self._callback_timeout if timeout is None else timeout
        wait_event = asyncio.Event()
        data = {"result": None}
        # Callback to wait and retrive data

        async def waiter_callback(answer):
            data["result"] = answer
            # Signal callback is done
            wait_event.set()

        await self.queue_url(url, waiter_callback, **kwargs)
        # Wait with timeout
        if timeout is not None:
            await asyncio.wait_for(wait_event.wait(), timeout)
        # wait forever
        else:
            await wait_event.wait()
        # return saved result value from callback
        return data["result"]

    async def queue_url(
        self,
        url: str,
        callback: Coroutine,
        config: Union[FetcherConfig, dict] = None,
        fetcher="HttpFetchProvider",
    ) -> FetchEvent:
        """Simplified default fetching handler for queuing a fetch task.

        Args:
            url (str): the URL to fetch from
            callback (Coroutine): a callback to call with the fetched result
            config (FetcherConfig, optional): Configuration to be used by the fetcher. Defaults to None.
            fetcher (str, optional): Which fetcher class to use. Defaults to "HttpFetchProvider".
        Returns:
            the queued event (which will be mutated to at least have an Id)

        Raises:
            @see self.queue_fetch_event
        """
        # override default fetcher with (potential) override value from FetcherConfig
        if isinstance(config, dict) and config.get("fetcher", None) is not None:
            fetcher = config["fetcher"]
        elif isinstance(config, FetcherConfig) and config.fetcher is not None:
            fetcher = config.fetcher

        # init a URL event
        event = FetchEvent(url=url, fetcher=fetcher, config=config)
        return await self.queue_fetch_event(event, callback)

    async def queue_fetch_event(
        self, event: FetchEvent, callback: Coroutine, enqueue_timeout=None
    ) -> FetchEvent:
        """Basic handler to queue a fetch event for a fetcher class. Waits if
        the queue is full until enqueue_timeout seconds; if enqueue_timeout is
        None returns immediately or raises QueueFull.

        Args:
            event (FetchEvent): the fetch event to queue as a task
            callback (Coroutine): a callback to call with the fetched result
            enqueue_timeout (float): timeout in seconds or None for no timeout, Defaults to self.DEFAULT_ENQUEUE_TIMEOUT

        Returns:
            the queued event (which will be mutated to at least have an Id)

        Raises:
            asyncio.QueueFull: if the queue is full and enqueue_timeout is set as None
            asyncio.TimeoutError: if enqueue_timeout is not None, and the queue is full and hasn't cleared by the timeout time
        """
        enqueue_timeout = (
            enqueue_timeout if enqueue_timeout is not None else self._enqueue_timeout
        )
        # Assign a unique identifier for the event
        event.id = self.gen_uid()
        # add to the queue for handling
        # if no timeout we return immediately or raise QueueFull
        if enqueue_timeout is None:
            await self._queue.put_nowait((event, callback))
        # if timeout
        else:
            await asyncio.wait_for(self._queue.put((event, callback)), enqueue_timeout)
        return event

    def create_worker(self) -> asyncio.Task:
        """Create an asyncio worker to work the engine's queue Engine init
        starts several workers according to given configuration."""
        task = asyncio.create_task(fetch_worker(self._queue, self))
        self._tasks.append(task)
        return task

    def register_failure_handler(self, callback: OnFetchFailureCallback):
        """Register a callback to be called with exception and original event
        in case of failure.

        Args:
            callback (OnFetchFailureCallback): callback to register
        """
        self._failure_handlers.append(callback)

    async def _management_event_handler(
        self, handlers: List[Coroutine], *args, **kwargs
    ):
        """
        Generic management event subscriber caller
        Args:
            handlers (List[Coroutine]): callback coroutines
        """
        await asyncio.gather(*(callback(*args, **kwargs) for callback in handlers))

    async def _on_failure(self, error: Exception, event: FetchEvent):
        """Call event failure subscribers.

        Args:
            error (Exception): thrown exception
            event (FetchEvent): event which was being handled
        """
        await self._management_event_handler(self._failure_handlers, error, event)
