from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

import aiohttp
from fastapi import status

from opal_server.redis import RedisDB
from opal_server.scopes.pull_engine import PullEngine
from opal_common.scopes.scopes import ScopeConfig, Scope


class ScopeNotFound(Exception):
    pass


class ScopeStore(ABC):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    @abstractmethod
    async def add_scope(self, scope_config: ScopeConfig) -> Scope:
        pass

    @abstractmethod
    async def get_scope(self, scope_id: str) -> Scope:
        pass

    @abstractmethod
    async def all_scopes(self) -> List[Scope]:
        pass


class PermitScopeStore(ScopeStore):
    PREFIX = 'io.permit.scope'

    def __init__(self, base_dir: str, permit_url: str, redis: RedisDB, puller: PullEngine):
        super(PermitScopeStore, self).__init__(base_dir)
        self._redis = redis
        self._permit_url = permit_url
        self._puller = puller

    async def all_scopes(self) -> List[Scope]:
        scopes = []

        for value in self._redis.scan(f'{self.PREFIX}:*'):
            scope = Scope.parse_raw(value)
            scopes.append(scope)

        return scopes

    async def get_scope(self, scope_id: str) -> Scope:
        value = await self._redis.get(self._redis_key(scope_id))

        if value:
            return Scope.parse_raw(value)

        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._permit_url}/scopes/{scope_id}') as response:
                if response.status == status.HTTP_200_OK:
                    config = ScopeConfig.parse_obj(await response.json())
                    scope = Scope(
                        scope_id=scope_id,
                        config=config
                    )

                    created = await self._redis.set_if_not_exists(
                        self._redis_key(scope_id),
                        scope,
                        ex_in_secs=60 * 60 * 6  # six hours
                    )

                    if created:
                        await self._puller.fetch_source(Path(self.base_dir), scope.config)

                    return scope
                else:
                    raise ScopeNotFound()

    async def add_scope(self, scope_config: ScopeConfig) -> Scope:
        raise NotImplementedError()

    def _redis_key(self, scope_id: str):
        return f'{self.PREFIX}:{scope_id}'


class LocalScopeStore(ScopeStore):
    def __init__(self, base_dir: str, pull_engine: PullEngine):
        super().__init__(base_dir)
        self.engine = pull_engine
        self.scopes: dict[str, Scope] = {}

    async def all_scopes(self) -> List[Scope]:
        return list(self.scopes.values())

    async def add_scope(self, scope_config: ScopeConfig) -> Scope:
        self._fetch_scope_from_source(scope_config)

        scope = Scope(
            config=scope_config,
            location=scope_config.scope_id,
        )
        self.scopes[scope_config.scope_id] = scope

        return scope

    async def get_scope(self, scope_id: str) -> Scope:
        if scope_id in self.scopes.keys():
            return self.scopes[scope_id]
        raise ScopeNotFound()

    def _fetch_scope_from_source(self, scope: ScopeConfig):
        self.engine.fetch_source(Path(self.base_dir), scope)


class ReadOnlyScopeStore(Exception):
    pass
