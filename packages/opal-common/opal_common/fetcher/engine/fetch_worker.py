import asyncio
from typing import Coroutine

from opal_common.fetcher.engine.base_fetching_engine import BaseFetchingEngine
from opal_common.fetcher.events import FetchEvent
from opal_common.fetcher.fetcher_register import FetcherRegister
from opal_common.fetcher.logger import get_logger

logger = get_logger("fetch_worker")


async def fetch_worker(queue: asyncio.Queue, engine):
    """The worker task performing items added to the Engine's Queue.

    Args:
        queue (asyncio.Queue): The Queue
        engine (BaseFetchingEngine): The engine itself
    """
    engine: BaseFetchingEngine
    register: FetcherRegister = engine.register
    while True:
        # types
        event: FetchEvent
        callback: Coroutine
        # get a event from the queue
        event, callback = await queue.get()
        # take care of it
        fetcher = res = data = None
        try:
            # get fetcher for the event
            fetcher = register.get_fetcher_for_event(event)
            # fetch
            async with fetcher:
                res = await fetcher.fetch()
                data = await fetcher.process(res)
            # callback to event owner
            try:
                await callback(data)
            except Exception as err:
                logger.exception(f"Fetcher callback - {callback} failed")
                await engine._on_failure(err, event)
        except Exception as err:
            logger.exception("Failed to process fetch event")
            await engine._on_failure(err, event)
        finally:
            # Notify the queue that the "work item" has been processed.
            queue.task_done()
            # Drop references to the processed event and its (potentially large)
            # fetched payload. Otherwise these locals stay bound in the worker's
            # frame while it blocks on the next `queue.get()`, so every idle
            # worker pins its last dataset + response in memory indefinitely
            # (one retained copy per worker -> a memory high-water mark that only
            # resets on process restart). See issues #770 / #844.
            event = callback = fetcher = res = data = None
