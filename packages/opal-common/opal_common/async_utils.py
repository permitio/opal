from __future__ import annotations

import asyncio
import sys
from functools import partial
from typing import Any, Callable, Coroutine, List, Optional, Tuple, TypeVar

import loguru

if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec
else:
    from typing import ParamSpec

T_result = TypeVar("T_result")
P_args = ParamSpec("P_args")


async def run_sync(
    func: Callable[P_args, T_result], *args: P_args.args, **kwargs: P_args.kwargs
) -> T_result:
    """Shorthand for running a sync function in an executor within an async
    context.

    For example:
        def sync_function_that_takes_time_to_run(arg1, arg2):
            time.sleep(5)

        async def async_function():
            await run_sync(sync_function_that_takes_time_to_run, 1, arg2=5)
    """
    return await asyncio.get_event_loop().run_in_executor(
        None, partial(func, *args, **kwargs)
    )


class TakeANumberQueue:
    """Enables a task to hold a place in queue prior to having the actual item
    to be sent over the queue.

    The goal is executing concurrent tasks while still processing their
    results by the original order of execution
    """

    class Number:
        def __init__(self):
            self._event = asyncio.Event()
            self._item = None

        def put(self, item: Any):
            self._item = item
            self._event.set()

        async def get(self) -> Any:
            await self._event.wait()
            return self._item

    def __init__(self, logger: loguru.Logger):
        self._queue: asyncio.Queue | None = None
        self._logger = logger

    async def take_a_number(self) -> Number:
        assert self._queue is not None, "Queue not initialized"
        n = TakeANumberQueue.Number()
        await self._queue.put(n)
        return n

    async def get(self) -> Any:
        n: TakeANumberQueue.Number = await self._queue.get()
        return await n.get()  # Wait for next in line to have a result

    async def _handle_queue(self, handler: Coroutine):
        self._queue = asyncio.Queue()
        while True:
            try:
                item = await self.get()
                await handler(item)
            except asyncio.CancelledError:
                if self._logger:
                    self._logger.debug("queue handling task cancelled")
                return
            except Exception:
                if self._logger:
                    self._logger.exception("failed handling take-a-number queue item")

    async def start_queue_handling(self, handler: Coroutine):
        self._handler_task = asyncio.create_task(self._handle_queue(handler))

    async def stop_queue_handling(self):
        if self._handler_task:
            self._handler_task.cancel()
            self._handler_task = None


class TasksPool:
    def __init__(self):
        self._tasks: List[asyncio.Task] = []

    def _cleanup_task(self, done_task):
        self._tasks.remove(done_task)

    def add_task(self, f):
        t = asyncio.create_task(f)
        self._tasks.append(t)
        t.add_done_callback(self._cleanup_task)


async def repeated_call(
    func: Coroutine,
    seconds: float,
    *args: Tuple[Any],
    logger: Optional[loguru.Logger] = None,
):
    while True:
        try:
            await func(*args)
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "Error during repeated call to {func}: {exc}",
                func=func,
                exc=exc,
            )
