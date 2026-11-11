from typing import AsyncIterator, Generator

import redis.asyncio as redis
from opal_common.http_utils import redact_url
from opal_common.logger import logger
from pydantic import BaseModel


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

    async def scan(self, pattern: str) -> Generator[bytes, None, None]:
        cur = b"0"
        while cur:
            cur, keys = await self._redis.scan(cur, match=pattern)

            for key in keys:
                value = await self._redis.get(key)
                yield value

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
