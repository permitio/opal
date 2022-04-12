from typing import TypeVar, Generic

import aioredis
from pydantic import BaseModel

T = TypeVar('T')


class RedisDB:
    def __init__(self, redis_url):
        self._redis = aioredis.from_url(redis_url)

    async def set(self, key: str, value: BaseModel, ex_in_secs=None):
        await self._redis.set(key, self._serialize(value), ex=ex_in_secs)

    async def set_if_not_exists(self, key: str, value: BaseModel, ex_in_secs=None) -> bool:
        '''
        :param key:
        :param value:
        :param ex_in_secs:
        :return: True if created, False if key already exists
        '''
        return await self._redis.set(key, self._serialize(value), nx=True, ex=ex_in_secs)

    async def get(self, key: str) -> bytes:
        return await self._redis.get(key)

    async def scan(self, pattern: str):
        cur = b'0'
        while cur:
            cur, keys = self._redis.scan(cur, match=pattern)

            for key in keys:
                value = await self._redis.get(key)
                yield value

    def _serialize(self, value: BaseModel) -> str:
        return value.json()

