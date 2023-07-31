import asyncio
import sys
from functools import partial
from typing import Callable, TypeVar

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

    For example:     def sync_function_that_takes_time_to_run(arg1,
    arg2):         time.sleep(5)     async def async_function():
    await run_sync(sync_function_that_takes_time_to_run, 1, arg2=5)
    """
    return await asyncio.get_event_loop().run_in_executor(
        None, partial(func, *args, **kwargs)
    )
