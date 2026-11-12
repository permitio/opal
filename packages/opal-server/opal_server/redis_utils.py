from typing import AsyncIterator, Optional

import redis.asyncio as redis
from opal_common.http_utils import redact_url
from opal_common.logger import logger
from pydantic import BaseModel

# SCAN's COUNT for scan(): how many keys Redis looks at per call, and so about
# how many GETs one pipeline sends. With 1,000, thousands of keys take a few
# round trips rather than one per key, and each reply stays small.
_SCAN_COUNT = 1000


class RedisDB:
    """Small utility class to persist objects in Redis."""

    def __init__(self, redis_url):
        self._url = redis_url
        logger.debug("Connecting to Redis: {url}", url=redact_url(self._url))

        self._redis = redis.Redis.from_url(self._url)

    @property
    def redis_connection(self) -> redis.Redis:
        return self._redis

    async def set(self, key: str, value: BaseModel):
        await self._redis.set(key, self._serialize(value))

    async def set_if_not_exists(self, key: str, value: BaseModel) -> bool:
        """:param key:
        :param value:
        :return: True if created, False if key already exists
        """

        return await self._redis.set(key, self._serialize(value), nx=True)

    async def get(self, key: str) -> bytes:
        return await self._redis.get(key)

    async def scan(self, pattern: str) -> AsyncIterator[Optional[bytes]]:
        """The value of every key that matches ``pattern``: a SCAN page of up
        to _SCAN_COUNT keys at a time, each page's values read with one
        pipeline of GETs (one round trip).

        Single-key commands only: an MGET of a page would span hash slots,
        which a Redis in cluster mode refuses (CROSSSLOT), even one whose
        every slot one node serves. A key deleted between the SCAN and its
        GET comes back as None, and a key SCAN returns more than once, more
        than once.
        """
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=pattern, count=_SCAN_COUNT
            )
            if keys:
                async with self._redis.pipeline(transaction=False) as pipe:
                    for key in keys:
                        pipe.get(key)
                    values = await pipe.execute()
                for value in values:
                    yield value
            if not cursor:
                return

    async def scan_keys(self, pattern: str, count: int) -> AsyncIterator[bytes]:
        """Every key that matches ``pattern``, read with SCAN alone.

        ``count`` is SCAN's COUNT, how many keys Redis looks at per call.
        A key can come more than once, as SCAN may return it more than once.
        """
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=count)
            for key in keys:
                yield key
            if not cursor:
                return

    async def delete(self, key: str):
        await self._redis.delete(key)

    async def close(self) -> None:
        """Close every connection the client's pool opened.

        close_connection_pool=True: from_url builds the client around a
        pool of its own making, which redis-py 4.x then treats as one it
        was given, and close() alone leaves it connected.
        """
        await self._redis.close(close_connection_pool=True)

    def _serialize(self, value: BaseModel) -> str:
        return value.model_dump_json()
