from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict

import aiohttp
from fastapi import status

from opal_server.scopes.pull_engine import PullEngine
from opal_server.scopes.scopes import ScopeConfig, Scope


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
    async def all_scopes(self) -> dict[str, Scope]:
        pass


class LocalScopeStore(ScopeStore):
    def __init__(self, base_dir: str, fetch_engine: PullEngine):
        super().__init__(base_dir)
        self.engine = fetch_engine
        self.scopes: dict[str, Scope] = {}

    async def all_scopes(self) -> dict[str, Scope]:
        return self.scopes

    async def add_scope(self, scope_config: ScopeConfig) -> Scope:
        task_id = self._fetch_scope_from_source(scope_config)

        scope = Scope(
            config=scope_config,
            location=scope_config.scope_id,
            task_id=task_id
        )
        self.scopes[scope_config.scope_id] = scope

        return scope

    async def get_scope(self, scope_id: str) -> Scope:
        if scope_id in self.scopes.keys():
            return self.scopes[scope_id]
        raise ScopeNotFound()

    def _fetch_scope_from_source(self, scope: ScopeConfig):
        return self.engine.fetch_source(Path(self.base_dir), scope)


class ReadOnlyScopeStore(Exception):
    pass


class RemoteScopeStore(ScopeStore):
    def __init__(self, base_dir: str, primary_url: str):
        super().__init__(base_dir)
        self.primary_url = primary_url

    async def add_scope(self, scope_config: ScopeConfig) -> Scope:
        raise ReadOnlyScopeStore()

    async def get_scope(self, scope_id: str) -> Scope:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self.primary_url}/api/v1/scopes/{scope_id}') as response:
                if response.status == status.HTTP_200_OK:
                    scope_config = ScopeConfig.parse_obj(await response.json())

                    return Scope(
                        config=scope_config,
                        location=scope_config.scope_id
                    )
                else:
                    raise ScopeNotFound()

    async def all_scopes(self) -> dict[str, Scope]:
        raise ReadOnlyScopeStore()
