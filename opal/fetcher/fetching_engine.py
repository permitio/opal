import asyncio
import uuid
import tenacity
from asyncio import events
from typing import Coroutine, Dict, List

from .events import FetcherConfig, FetchEvent
from .fetch_provider import BaseFetchProvider
from .fetcher_register import FetcherRegister
from .logger import get_logger

logger = get_logger("engine")


# Callback signatures 
async def OnFetchFailureCallback(exception:Exception, event: FetchEvent):
    """
    Args:
        exception (Exception): The exception thrown causing the failure 
        event (FetchEvent): the queued event which failed
    """
    pass


async def fetch_worker(queue: asyncio.Queue, engine):
    """
    The worker task performing items added to the Engine's Queue

    Args:
        queue (asyncio.Queue): The Queue 
        engine (FetchingEnging): The engine itself
    """
    engine: FetchingEngine
    register: FetcherRegister = engine.register
    
    while True:
        # types
        event: FetchEvent
        callback: Coroutine
        # get a event from the queue
        event, callback = await queue.get()
        # take care of it
        try:
            # get fetcher for the event
            fetcher = register.get_fetcher_for_event(event)
            assert fetcher is not None
            # fetch
            data = await fetcher.fetch()
            # callback to event owner
            try:
                await callback(data)
            except Exception as err:
                logger.exception(f"Callback - {callback} failed")
                engine.on_failure(err, event)
        except tenacity.RetryError as err:
            logger.exception("Fetch event retries have timed-out")
            engine.on_failure(err, event)
        except Exception as err:
            logger.exception("Failed to process fetch event")
            engine.on_failure(err, event)
        finally:
            # Notify the queue that the "work item" has been processed.
            queue.task_done()


class FetchingEngine:
    """
    A Task queue manager for fetching events.

    - Configure with different fetcher providers - via __init__'s register_config or via self.register.register_fetcher()
    - Use queue_url() to fetch a given URL with the default FetchProvider
    - Use queue_fetch_event() to fetch data using a configured FetchProvider
    - Use with 'async with' to terminate tasks (or call self.terminate_tasks() when done)
    """

    DEFAULT_WORKER_COUNT = 5

    @staticmethod
    def gen_uid():
        return uuid.uuid4().hex

    def __init__(self, register_config:Dict[str, BaseFetchProvider]=None, worker_count=DEFAULT_WORKER_COUNT) -> None:
        # The internal task queue
        self._queue = asyncio.Queue()
        # Worker working the queue
        self._tasks = []
        # register of the fetch providers workers can use
        self._fetcher_register = FetcherRegister(register_config)
        # core event callback regsiters
        self._failure_handlers:List[OnFetchFailureCallback] = []
        
        # create worker tasks
        for _ in range(worker_count):
            self.create_worker()

    @property
    def register(self)->FetcherRegister:
        return self._fetcher_register

    async def __aenter__(self):
        """
        Async Context manager to cancel tasks on exit 
        """
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if (exc is not None):
            logger.error("Error occurred within FetchingEngine context", exc_info=(exc_type, exc, tb))
        await self.terminate_tasks()

    async def terminate_tasks(self):
        """
        Cancel and wait on the internal worker tasks
        """
        # Cancel our worker tasks.
        for task in self._tasks:
            task.cancel()
        # Wait until all worker tasks are cancelled.
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def queue_url(self, url: str, callback: Coroutine, config: FetcherConfig = None, fetcher="HttpGetFetchProvider")->FetchEvent:
        """
        Simplified default fetching handler for queuing a fetch task

        Args:
            url (str): the URL to fetch from
            callback (Coroutine): a callback to call with the fetched result
            config (FetcherConfig, optional): Configuration to be used by the fetcher. Defaults to None.
            fetcher (str, optional): Which fetcher class to use. Defaults to "HttpGetFetchProvider".
        Returns: 
            the queued event (which will be mutated to at least have an Id)
        """
        # init a URL event
        event = FetchEvent(url=url, fetcher=fetcher, config=config)
        return await self.queue_fetch_event(event, callback)

    async def queue_fetch_event(self, event: FetchEvent, callback: Coroutine)->FetchEvent:
        """
        Basic handler to queue a fetch event for a fetcher class.
        Waits if the queue is full.

        Args:
            event (FetchEvent): the fetch event to queue as a task
            callback (Coroutine): a callback to call with the fetched result
        Returns: 
            the queued event (which will be mutated to at least have an Id)            
        """
        # Assign a unique identifier for the event 
        event.id = self.gen_uid()
        # add to the queue for handling
        await self._queue.put((event, callback))
        return event

    def create_worker(self) -> asyncio.Task:
        """
        Create an asyncio worker tak to work the engine's queue
        Engine init starts several workers according to given configuration
        """
        task = asyncio.create_task(fetch_worker(self._queue, self))
        self._tasks.append(task)
        return task


    def register_failure_handler(self, callback : OnFetchFailureCallback):
        """
        Register a callback to be called with exception and original event in case of failure

        Args:
            callback (OnFetchFailureCallback): callback to register
        """
        self._failure_handlers.append(callback)

    async def _management_event_handler(self, handlers:List[Coroutine], *args, **kwargs):
        """
        Generic management event subscriber caller
        Args:
            handlers (List[Coroutine]): callback coroutines
        """
        await asyncio.gather(*(callback(*args, **kwargs) for callback in handlers)) 

    async def _on_failure(self, error:Exception, event: FetchEvent):
        """
        Call event failure subscribers

        Args:
            error (Exception): thrown exception
            event (FetchEvent): event which was being handled
        """
        await self.on_handler_event(self._failure_handlers, error, event)
