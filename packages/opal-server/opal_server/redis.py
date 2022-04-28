from typing import Generator

import aioredis
from pydantic import BaseModel


class RedisDB:
    """
    Small utility class to persist objects in Redis
    """
    def __init__(self, redis_url):
        self._url = redis_url
        self._redis = aioredis.from_url(self._url)

    async def set(self, key: str, value: BaseModel, ex_in_secs=None):
        await self._redis.set(key, self._serialize(value), ex=ex_in_secs)

    async def set_if_not_exists(self, key: str, value: BaseModel, ex_in_secs=None) -> bool:
        '''
        :param key:
        :param value:
        :param ex_in_secs:
        :return: True if created, False if key already exist                    s
        '''
        return await self._redis.set(key, self._serialize(value), nx=True, ex=ex_in_secs)

    async def get(self, key: str) -> bytes:
        return await self._redis.get(key)

    async def scan(self, pattern: str) -> Generator[bytes]:
        cur = b'0'
        while cur:
            cur, keys = self._redis.scan(cur, match=pattern)

            for key in keys:
                value = await self._redis.get(key)
                yield value

    async def delete(self, key: str):
        await self._redis.delete(key)

    def _serialize(self, value: BaseModel) -> str:
        return value.json()

