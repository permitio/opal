from typing import Generator

import aioredis
from opal_common.logger import logger
from pydantic import BaseModel


class RedisDB:
    """Small utility class to persist objects in Redis."""

    def __init__(self, redis_url):
        self._url = redis_url
        logger.debug("Connecting to Redis: {url}", url=self._url)

        self._redis = aioredis.from_url(self._url)

    @property
    def redis_connection(self) -> aioredis.Redis:
        return self._redis

    async def set(self, key: str, value: BaseModel):
        await self._redis.set(key, self._serialize(value))

    async def set_if_not_exists(self, key: str, value: BaseModel) -> bool:
        """
        :param key:
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

    async def delete(self, key: str):
        await self._redis.delete(key)

    def _serialize(self, value: BaseModel) -> str:
        return value.json()
