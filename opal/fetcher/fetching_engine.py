import asyncio
import typing
import tenacity
from asyncio import events
from typing import Coroutine, Dict

from .events import FetcherConfig, FetchEvent
from .fetch_provider import BaseFetchProvider
from .fetcher_register import FetcherRegister
from .logger import get_logger

logger = get_logger("engine")


async def fetch_worker(queue:asyncio.Queue, arsenal:FetcherRegister):
    """
    The worker task performing items added to the Engine's Queue

    Args:
        queue (asyncio.Queue): [description]
        arsenal (FetcherArsenal): [description]
    """

    while True:
        event: FetchEvent
        callback: Coroutine
        event, callback = await queue.get()
        try:
            fetcher = arsenal.get_fetcher_for_event(event)            
            assert fetcher is not None
            data = await fetcher.fetch()
            try:
                await callback(data)
            except: 
                logger.exception(f"Callback - {callback} failed")
        except tenacity.RetryError:
            logger.exception("Fetch event retries have timed-out")
        except:
            logger.exception("Failed to process fetch event")
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

    DEFAULT_WORKER_COUNT=5
    
    def __init__(self, register_config=Dict[str, BaseFetchProvider], worker_count=DEFAULT_WORKER_COUNT) -> None:
        self._queue = asyncio.Queue()
        self._tasks = []
        self._fetcher_register = FetcherRegister(register_config)
        # create worker tasks
        for _ in range(worker_count):
            self.create_worker()

    @property
    def register(self):
        return self._fetcher_register

    async def __aenter__(self):
        """
        Async Context manager to cancel tasks on exit 
        """
        return self

    async def  __aexit__(self, exc_type, exc, tb):
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

    async def queue_url(self, url:str, callback:Coroutine, config:FetcherConfig=None, fetcher="HttpGetFetchProvider"):
        """
        Simplified default fetching handler for queuing a fetch task

        Args:
            url (str): the URL to fetch from
            callback (Coroutine): a callback to call with the fetched result
            config (FetcherConfig, optional): Configuration to be used by the fetcher. Defaults to None.
            fetcher (str, optional): Which fetcher class to use. Defaults to "HttpGetFetchProvider".
        """
        #init a URL event
        event = FetchEvent(url=url, fetcher=fetcher, config=config)
        await self.queue_fetch_event(event, callback)

    async def queue_fetch_event(self, event:FetchEvent, callback:Coroutine):
        """Basic handler to queue a fetch event for a fetcher class

        Args:
            event (FetchEvent): the fetch event to queue as a task
            callback (Coroutine): a callback to call with the fetched result
        """
        # add to the queue for handling
        await self._queue.put((event, callback))


    def create_worker(self)-> asyncio.Task:
        """
        Create an asyncio worker tak to work the engine's queue
        Engine init starts several workers according to given configuration
        """
        task = asyncio.create_task(fetch_worker(self._queue, self._fetcher_register))
        self._tasks.append(task)
        return task
