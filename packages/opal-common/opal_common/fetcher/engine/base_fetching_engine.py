from typing import Coroutine

from ..events import FetcherConfig, FetchEvent
from ..fetcher_register import FetcherRegister
from .core_callbacks import OnFetchFailureCallback


class BaseFetchingEngine:
    """An interface base class for a task queue manager used for fetching
    events."""

    @property
    def register(self) -> FetcherRegister:
        """access to the underlying fetcher providers register."""
        raise NotImplementedError()

    async def __aenter__(self):
        """Async Context manager to cancel tasks on exit."""
        raise NotImplementedError()

    async def __aexit__(self, exc_type, exc, tb):
        raise NotImplementedError()

    async def terminate_tasks(self):
        """Cancel and wait on the internal worker tasks."""
        raise NotImplementedError()

    async def queue_url(
        self,
        url: str,
        callback: Coroutine,
        config: FetcherConfig = None,
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
        """
        raise NotImplementedError()

    async def queue_fetch_event(
        self, event: FetchEvent, callback: Coroutine
    ) -> FetchEvent:
        """Basic handler to queue a fetch event for a fetcher class. Waits if
        the queue is full.

        Args:
            event (FetchEvent): the fetch event to queue as a task
            callback (Coroutine): a callback to call with the fetched result
        Returns:
            the queued event (which will be mutated to at least have an Id)
        """
        raise NotImplementedError()

    def register_failure_handler(self, callback: OnFetchFailureCallback):
        """Register a callback to be called with exception and original event
        in case of failure.

        Args:
            callback (OnFetchFailureCallback): callback to register
        """
        raise NotImplementedError()

    async def _on_failure(self, error: Exception, event: FetchEvent):
        """Call event failure subscribers.

        Args:
            error (Exception): thrown exception
            event (FetchEvent): event which was being handled
        """
        raise NotImplementedError()
