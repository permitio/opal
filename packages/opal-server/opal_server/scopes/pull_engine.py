from abc import ABC, abstractmethod
from pathlib import Path

from opal_server.scopes.pullers import create_puller
from opal_server.scopes.scopes import ScopeConfig


class PullEngine(ABC):
    @abstractmethod
    def fetch_source(self, base_dir: Path, scope: ScopeConfig):
        pass


class CeleryPullEngine(PullEngine):
    def fetch_source(self, base_dir: Path, scope: ScopeConfig):
        from opal_server import worker
        result = worker.fetch_source.delay(str(base_dir), scope.json())
        return result.task_id


class LocalPullEngine(PullEngine):
    def fetch_source(self, base_dir: Path, scope: ScopeConfig):
        create_puller(base_dir, scope).pull()
        return "{local}"
