from abc import ABC, abstractmethod
from pathlib import Path

from opal_server.scopes.pullers import create_puller
from opal_common.scopes.scopes import ScopeConfig


class PullEngine(ABC):
    @abstractmethod
    async def fetch_source(self, base_dir: Path, scope: ScopeConfig):
        pass


class CeleryPullEngine(PullEngine):
    async def fetch_source(self, base_dir: Path, scope: ScopeConfig):
        from opal_server import worker
        worker.fetch_source.delay(str(base_dir), scope.json())


class LocalPullEngine(PullEngine):
    async def fetch_source(self, base_dir: Path, scope: ScopeConfig):
        create_puller(base_dir, scope).pull()
