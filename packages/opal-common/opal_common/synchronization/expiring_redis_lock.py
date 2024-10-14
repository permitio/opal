import asyncio

import redis.asyncio as redis
from opal_common.logger import logger


async def run_locked(
    _redis: redis.Redis, lock_name: str, coro: asyncio.coroutine, timeout: int = 10
):
    """This function runs a coroutine wrapped in a redis lock, in a way that
    prevents hanging locks. Hanging locks can happen when a process crashes
    while holding a lock.

    This function sets a redis enforced timeout, and reacquires the lock
    every timeout * 0.8 (as long as it runs)
    """
    lock = _redis.lock(lock_name, timeout=timeout)
    try:
        logger.debug(f"Trying to acquire redis lock: {lock_name}")
        await lock.acquire()
        logger.debug(f"Acquired lock: {lock_name}")

        locked_task = asyncio.create_task(coro)

        while True:
            done, _ = await asyncio.wait(
                (locked_task,),
                timeout=timeout * 0.8,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if locked_task in done:
                break
            else:
                # Extend lock timeout as long as the coroutine is still running
                await lock.reacquire()
                logger.debug(f"Reacquired lock: {lock_name}")

    finally:
        await lock.release()
        logger.debug(f"Released lock: {lock_name}")
