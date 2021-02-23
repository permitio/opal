import asyncio
from asyncio import events
from typing import Coroutine
from .events import FetchEvent
from .fetcher_arsenal import FetcherArsenal
from .data_fetcher import BaseFetchProvider


async def fetch_worker(queue:asyncio.Queue, arsenal:FetcherArsenal):

    while True:
        event: FetchEvent
        callback: Coroutine
        event, callback = await queue.get()
        try:
            fetcher = arsenal.get_fetcher_for_event(event)
            assert fetcher is not None
            data = await fetcher.fetch()
            await callback(data)
        finally:
            # Notify the queue that the "work item" has been processed.
            queue.task_done()



class FetchingEngine:
    
    
    def __init__(self, arsenal_config=None, worker_count=4) -> None:
        self._queue = asyncio.Queue()
        self._tasks = []
        self._fetcher_arsenal = FetcherArsenal(arsenal_config)
        # create worker tasks
        for _ in range(worker_count):
            self.create_worker()


    def handle_url(self, url, callback:Coroutine):
        event = FetchEvent(url=url, fetcher="HttpGetFetchProvider")
        return self.handle_fetch_event(event, callback)

    def handle_fetch_event(self, event:FetchEvent, callback:Coroutine):
        # add to the queue for handling
        self._queue.put_nowait((event, callback))


    def create_worker(self)-> asyncio.Task:
        task = asyncio.create_task(fetch_worker(self._queue, self._fetcher_arsenal))
        self._tasks.append(task)
        return task